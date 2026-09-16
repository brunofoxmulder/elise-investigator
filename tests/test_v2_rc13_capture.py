from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "elise_investigator/app"))
from activity_reader_rc12 import ActivityTraceReaderRC12
from activity_reader_rc13 import ActivityTraceReaderRC13
from causal_recorder import CausalRecorder
from proof_archive_rc13 import PROOF_KEY, ProofArchive
from proof_capture_rc13 import ProofCapture, ObservedMemoryStream
from test_v2_rc12_start_trigger_chain import ReadOnlyHA, TraceInvestigator, trace, SOURCE, STAMP, TARGETS

STAMP_DT = datetime.fromisoformat(STAMP)


class LiveHA(ReadOnlyHA):
    def __init__(self):
        super().__init__(trace(), TARGETS[0])
        self.available = True
        self.entries = [{"entity_id": self.target, "state": "on", "when": STAMP,
                         "context_entity_id": SOURCE, "context_source": "state of binary_sensor.tariff_window",
                         "context_message": "triggered by state of binary_sensor.tariff_window"}]
        self.reads = 0

    async def get_logbook(self, entity, start, end):
        return deepcopy([e for e in self.entries if e["entity_id"] == entity and start <= datetime.fromisoformat(e["when"]) < end])

    async def list_traces(self, domain, item_id):
        self.reads += 1
        return await super().list_traces(domain, item_id) if self.available else []


def event(stamp=STAMP, before="off", after="on", entity=TARGETS[0]):
    return {"event_type": "state_changed", "time_fired": stamp, "data": {"entity_id": entity,
        "old_state": {"state": before, "attributes": {}},
        "new_state": {"state": after, "last_changed": stamp, "attributes": {}}}}


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3")
        self.now = STAMP_DT + timedelta(minutes=1)
        self.archive = ProofArchive(self.recorder, clock=lambda: self.now)
        self.ha = LiveHA()
        self.reader = ActivityTraceReaderRC13(self.ha, TraceInvestigator())
        self.reader.archive = self.archive
        self.capture = ProofCapture(self.reader, self.archive)

    async def asyncTearDown(self):
        await self.capture.stop()
        self.recorder.close(); self.tmp.cleanup()

    async def read(self, reader=None):
        return await (reader or self.reader)._record_from_entries(TARGETS[0], deepcopy(self.ha.entries),
            end_time=self.now, hours=12, allow_upstream=False)

    async def test_rc12_reproduces_loss_and_rc13_retains_same_event_after_eviction(self):
        baseline = ActivityTraceReaderRC12(self.ha, TraceInvestigator())
        previous = await self.read(baseline)
        saved = await self.read()
        self.assertTrue(previous.reason); self.assertEqual(saved.reason, previous.reason)
        self.assertIn(PROOF_KEY, saved.trigger)
        self.ha.available = False
        self.assertIsNone((await self.read(baseline)).reason)
        retained = await self.read()
        self.assertEqual(retained.reason, previous.reason)
        self.assertEqual(retained.reason_code, "ha_logbook+retained_exact_trace")

    async def test_background_captures_without_any_user_question(self):
        self.capture.RETRIES = (0, .001)
        await self.capture.start()
        self.capture.enqueue(event())
        for _ in range(50):
            if self.capture.captured: break
            await asyncio.sleep(.002)
        self.assertEqual(self.capture.captured, 1)
        self.ha.available = False
        self.assertTrue((await self.read()).reason)

    async def test_same_state_new_movement_does_not_inherit_old_reason(self):
        await self.read()
        self.ha.available = False
        self.ha.entries[0]["when"] = (STAMP_DT + timedelta(seconds=30)).isoformat()
        self.assertIsNone((await self.read()).reason)

    async def test_missing_logbook_never_returns_cached_event(self):
        await self.read(); self.ha.entries = []
        self.assertIsNone(await self.read())

    async def test_missing_trace_without_previous_proof_stays_unknown(self):
        self.ha.available = False
        self.assertIsNone((await self.read()).reason)

    async def test_database_failure_preserves_live_rc12_answer(self):
        self.archive.save = lambda _: (_ for _ in ()).throw(OSError("disk full"))
        self.assertTrue((await self.read()).reason)
        self.assertEqual(self.reader.archive_failures, 1)

    async def test_capture_retries_until_logbook_is_committed(self):
        entries = self.ha.entries; self.ha.entries = []
        self.capture.RETRIES = (.001, .01, .02)
        await self.capture.start(); self.capture.enqueue(event())
        await asyncio.sleep(.005)
        self.ha.entries = entries
        for _ in range(50):
            if self.capture.captured: break
            await asyncio.sleep(.003)
        self.assertEqual(self.capture.captured, 1)

    async def test_rapid_events_are_read_at_their_own_time_not_latest(self):
        await self.read()
        self.ha.entries.append({**self.ha.entries[0], "when": (STAMP_DT + timedelta(seconds=20)).isoformat(), "state": "off"})
        self.ha.available = False
        self.assertTrue(await self.capture.capture_once((TARGETS[0], STAMP, "on")))

    async def test_no_periodic_reads_or_attribute_noise_or_availability_recovery(self):
        self.capture.enqueue(event(before="on", after="on"))
        self.capture.enqueue(event(before="unavailable"))
        self.capture.enqueue(event(entity="sensor.power", after="12"))
        self.capture.enqueue(event(entity="cover.blind", before="closed", after="opening"))
        await self.capture.start(); await asyncio.sleep(.01)
        self.assertEqual(self.ha.reads, 0)
        self.assertEqual(self.capture.status()["pending"], 0)

    async def test_queue_deduplicates_and_has_fixed_capacity(self):
        self.capture.CAPACITY = 2
        self.capture.enqueue(event()); self.capture.enqueue(event())
        self.capture.enqueue(event((STAMP_DT + timedelta(seconds=1)).isoformat()))
        self.capture.enqueue(event((STAMP_DT + timedelta(seconds=2)).isoformat()))
        self.assertEqual(self.capture.status()["pending"], 2)
        self.assertEqual(self.capture.dropped, 1)

    async def test_timeout_is_bounded_and_task_stops_cleanly(self):
        self.capture.RETRIES = (0, 0)
        self.capture.READ_TIMEOUT = .001
        async def slow(_):
            await asyncio.sleep(60)
        self.capture.capture_once = slow
        await self.capture.start(); self.capture.enqueue(event())
        for _ in range(50):
            if self.capture.missed: break
            await asyncio.sleep(.002)
        self.assertEqual(self.capture.errors, 2)
        self.assertEqual(self.capture.missed, 1)
        await self.capture.stop()
        self.assertFalse(self.capture.status()["running"])
        self.assertEqual(self.capture.status()["pending"], 0)

    async def test_existing_event_stream_gets_all_events_unchanged(self):
        events = [event(), {"event_type": "automation_triggered", "data": {}}]
        class Stream:
            async def events(self):
                for item in events: yield item
        received = [item async for item in ObservedMemoryStream(Stream(), self.capture).events()]
        self.assertEqual(received, events)
        self.assertIs(received[0], events[0])

    async def test_cover_terminal_proof_survives_five_new_traces_and_database_restart(self):
        target = "cover.solar_blind"
        self.ha.target = target
        opened = (STAMP_DT + timedelta(seconds=15)).isoformat()
        self.ha.entries = [
            {"entity_id": target, "state": "opening", "when": STAMP,
             "context_entity_id": SOURCE, "context_message": "triggered by time pattern"},
            {"entity_id": target, "state": "open", "when": opened}]
        command = {"action": "cover.set_cover_position", "target": {"entity_id": target},
                   "data": {"position": "{{ position_corrigee }}"}}
        self.ha.detail = {
            "config": {"triggers": [{"trigger": "time_pattern", "minutes": "/10"}],
                "actions": [{"variables": {"temperature": "{{ states('sensor.outdoor') }}",
                             "position_corrigee": "{{ 100 }}"}}, command]},
            "trace": {
                "trigger/0": [{"timestamp": STAMP, "changed_variables": {"trigger": {"platform": "time_pattern", "minutes": "/10"}}}],
                "action/0": [{"timestamp": STAMP, "changed_variables": {"temperature": 21.3, "position_corrigee": 100}}],
                "action/1": [{"timestamp": STAMP, "result": {"params": {"domain": "cover", "service": "set_cover_position",
                    "target": {"entity_id": target}, "service_data": {"position": 100}}}}]}}
        self.assertTrue(await self.capture.capture_once((target, opened, "open")))
        original = await self.reader._investigate_at(target, end_time=self.now, hours=12, allow_upstream=False)
        self.assertIn("100 %", original.reason)
        self.assertEqual(original.trigger[PROOF_KEY]["cause"]["detail"]["runtime_inputs"]["temperature"], 21.3)
        self.ha.available = False
        # HA still has five later runs, all of which aborted without a target action.
        async def later_traces(*_):
            return [{"run_id": f"later-{i}", "timestamp": {"start": (STAMP_DT + timedelta(minutes=10*i)).isoformat()}}
                    for i in range(1, 6)]
        self.ha.list_traces = later_traces
        self.ha.detail = {"config": {}, "trace": {}}
        self.now += timedelta(minutes=55)
        self.recorder.close()
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3")
        self.archive = ProofArchive(self.recorder, clock=lambda: self.now)
        self.reader = ActivityTraceReaderRC13(self.ha, TraceInvestigator()); self.reader.archive = self.archive
        retained = await self.reader._investigate_at(target, end_time=self.now, hours=12, allow_upstream=False)
        self.assertEqual(retained.reason, original.reason)
        self.assertEqual(retained.event_time, original.event_time)
        self.assertEqual(retained.reason_code, "ha_logbook+retained_exact_trace")

    async def test_request_path_keeps_exact_event_and_memory_provenance(self):
        import main_dev63
        from main_v2_rc11 import _answer_with_event_age
        from models import InvestigationRequest
        from unittest.mock import patch
        from types import SimpleNamespace
        await self.read(); self.ha.available = False
        self.reader.investigate = AsyncMock(side_effect=lambda *a, **k: self.read())
        # AsyncMock does not await an async-returning synchronous side effect.
        async def investigate(*args, **kwargs): return await self.read()
        self.reader.investigate = investigate
        app = {"activity_reader_dev63": self.reader, "ha": self.ha,
               "causal_settings": SimpleNamespace(retention_hours=12)}
        with patch.object(main_dev63, "_answer", _answer_with_event_age):
            body = await main_dev63._activity_payload(app, InvestigationRequest(entity_id=TARGETS[0]))
        self.assertTrue(body["cause_found"])
        self.assertEqual(body["event_time"], STAMP)
        self.assertEqual(body["reason_code"], "ha_logbook+retained_exact_trace")
        self.assertNotIn(PROOF_KEY, str(body))
