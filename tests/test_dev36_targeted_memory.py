from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import memory_worker_dev36 as worker_module
from causal_recorder import CausalRecord
from causal_recorder_dev33 import RelevantCausalRecorder
from memory_response_dev34 import answer_from_memory
from memory_worker_dev36 import TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev36 import TargetedMemoryEnricher, _select_logbook_entry

BASE = datetime(2026, 8, 28, 21, 0, tzinfo=timezone.utc)


def iso(seconds: float = 0) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


def record(*, after="on", context="ctx-good", entity_id="light.hotte") -> CausalRecord:
    return CausalRecord(
        entity_id=entity_id,
        entity_name="Hotte",
        event_time=iso(2),
        event_kind="turned_on" if after == "on" else "turned_off",
        before_value="off" if after == "on" else "on",
        after_value=after,
        origin_type="unknown",
        confidence="confirmed",
        trigger={"effect_context_id": context, "effect_parent_id": None},
    )


def motion_trace(*, after="on", target="light.hotte", platform="state") -> dict:
    trigger = {
        "platform": platform,
        "entity_id": "binary_sensor.mouvement_hotte",
        "to": after,
        "to_state": {
            "state": after,
            "attributes": {
                "friendly_name": "Mouvement hotte",
                "device_class": "motion",
            },
        },
    }
    return {
        "run_id": "run-1",
        "timestamp": {"start": iso(0), "finish": iso(3)},
        "trigger": trigger,
        "trace": {
            "action/0": [
                {
                    "path": "action/0",
                    "timestamp": iso(1),
                    "result": {
                        "params": {
                            "domain": "light",
                            "service": "turn_on" if after == "on" else "turn_off",
                            "target": {"entity_id": target},
                            "service_data": {},
                        }
                    },
                }
            ]
        },
    }


class FakeHA:
    def __init__(self, entries):
        self.entries = entries
        self.logbook_calls = 0
        self.state_calls = 0

    async def get_logbook(self, entity_id, start, end):
        self.logbook_calls += 1
        return list(self.entries)

    async def get_state(self, entity_id):
        self.state_calls += 1
        return {
            "entity_id": entity_id,
            "state": "on",
            "attributes": {
                "friendly_name": "Mouvement hotte",
                "device_class": "motion",
            },
        }


class FakeTraceInvestigator:
    def __init__(self, detail=None, *, raises=False):
        self.detail = detail
        self.raises = raises
        self.calls = 0

    async def _best_trace_for_source(self, source_entity_id, event_time):
        self.calls += 1
        if self.raises:
            raise RuntimeError("trace/get forbidden")
        if self.detail is None:
            return None
        return {
            "summary": {"run_id": self.detail.get("run_id", "run-1")},
            "detail": self.detail,
        }


class FakeProtocol:
    def __init__(self, *, after="on", target="light.hotte"):
        self.after = after
        self.target = target
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if arguments.get("run_id"):
            trace = motion_trace(after=self.after, target=self.target)
            action = trace["trace"]["action/0"][0]
            return {
                "structuredContent": {
                    "success": True,
                    "automation_id": arguments["automation_id"],
                    "run_id": "run-mcp",
                    "timestamp": trace["timestamp"],
                    "trigger": trace["trigger"],
                    "action_trace": [action],
                }
            }
        return {
            "structuredContent": {
                "traces": [
                    {
                        "run_id": "run-mcp",
                        "timestamp": {"start": iso(0), "finish": iso(3)},
                        "state": "stopped",
                    }
                ]
            }
        }


class FakeMCPClient:
    def __init__(self, protocol):
        self.protocol = protocol

    async def open_protocol(self):
        return None, self.protocol


class DummyEnricher:
    def __init__(self, ha, investigator):
        self.ha = ha
        self.investigator = investigator


class TestDev36TargetedMemory(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def recorder(self):
        return RelevantCausalRecorder(self.root / "memory.sqlite3")

    @staticmethod
    def automation_entry(*, context="ctx-good", when=2, state="on"):
        return {
            "when": iso(when),
            "entity_id": "light.hotte",
            "state": state,
            "context_id": context,
            "context_event_type": "automation_triggered",
            "context_entity_id": "automation.hotte_mouvement",
            "context_entity_id_name": "Hotte mouvement",
            "context_source": "state of binary_sensor.mouvement_hotte",
        }

    async def test_exact_context_beats_closer_wrong_logbook_entry(self):
        item = record()
        entries = [
            self.automation_entry(context="wrong", when=2.0),
            self.automation_entry(context="ctx-good", when=4.0),
        ]
        selected = _select_logbook_entry(entries, item)
        self.assertIsNotNone(selected)
        self.assertEqual(selected["context_id"], "ctx-good")

    async def test_motion_automation_becomes_functional_reason_from_one_source_trace(self):
        rec = self.recorder()
        stored = rec.record(record())
        ha = FakeHA([self.automation_entry()])
        traces = FakeTraceInvestigator(motion_trace())
        enricher = TargetedMemoryEnricher(ha, traces).bind_recorder(rec)

        changed = await enricher.enrich([stored])
        result = rec.get(stored.record_id)

        self.assertTrue(changed)
        self.assertEqual(ha.logbook_calls, 1)
        self.assertEqual(traces.calls, 1)
        self.assertEqual(enricher.trace_reads, 1)
        self.assertEqual(result.origin_type, "automation")
        self.assertEqual(result.reason, "un mouvement a été détecté")
        self.assertEqual(result.source_entity_id, "automation.hotte_mouvement")
        self.assertEqual(result.trigger["trace_backend"], "direct_ha")
        self.assertIn("mouvement", answer_from_memory(result))
        rec.close()

    async def test_direct_user_logbook_context_never_reads_a_trace(self):
        rec = self.recorder()
        stored = rec.record(record())
        ha = FakeHA(
            [
                {
                    "when": iso(2),
                    "entity_id": "light.hotte",
                    "state": "on",
                    "context_id": "ctx-good",
                    "context_user_id": "user-1",
                    "context_event_type": "call_service",
                    "context_domain": "light",
                    "context_service": "turn_on",
                }
            ]
        )
        traces = FakeTraceInvestigator(motion_trace())
        enricher = TargetedMemoryEnricher(ha, traces).bind_recorder(rec)

        await enricher.enrich([stored])
        result = rec.get(stored.record_id)

        self.assertEqual(result.origin_type, "user")
        self.assertEqual(traces.calls, 0)
        self.assertIn("commande utilisateur", answer_from_memory(result))
        rec.close()

    async def test_technical_time_pattern_is_not_a_functional_reason(self):
        rec = self.recorder()
        stored = rec.record(record(entity_id="cover.volet_salon_2"))
        entry = self.automation_entry()
        entry["entity_id"] = "cover.volet_salon_2"
        entry["context_entity_id"] = "automation.gestion_volet_salon"
        ha = FakeHA([entry])
        detail = motion_trace(target="cover.volet_salon_2", platform="time_pattern")
        detail["trigger"] = {"platform": "time_pattern", "minutes": "/10"}
        detail["trace"]["action/0"][0]["result"]["params"] = {
            "domain": "cover",
            "service": "set_cover_position",
            "target": {"entity_id": "cover.volet_salon_2"},
            "service_data": {"position": 40},
        }
        traces = FakeTraceInvestigator(detail)
        enricher = TargetedMemoryEnricher(ha, traces).bind_recorder(rec)

        await enricher.enrich([stored])
        result = rec.get(stored.record_id)

        self.assertEqual(result.origin_type, "automation")
        self.assertIsNone(result.reason)
        self.assertEqual(answer_from_memory(result), "Je n'ai pas trouvé la cause.")
        rec.close()

    async def test_nearby_trace_without_executed_target_command_is_rejected(self):
        rec = self.recorder()
        stored = rec.record(record())
        ha = FakeHA([self.automation_entry()])
        traces = FakeTraceInvestigator(motion_trace(target="light.autre"))
        enricher = TargetedMemoryEnricher(ha, traces).bind_recorder(rec)

        await enricher.enrich([stored])
        result = rec.get(stored.record_id)

        self.assertEqual(result.origin_type, "automation")
        self.assertIsNone(result.reason)
        self.assertEqual(answer_from_memory(result), "Je n'ai pas trouvé la cause.")
        rec.close()

    async def test_mcp_exact_source_trace_is_used_when_direct_trace_api_is_refused(self):
        rec = self.recorder()
        stored = rec.record(record())
        ha = FakeHA([self.automation_entry()])
        traces = FakeTraceInvestigator(raises=True)
        protocol = FakeProtocol()
        enricher = TargetedMemoryEnricher(ha, traces).bind_recorder(rec)
        enricher.set_mcp_client(FakeMCPClient(protocol))

        await enricher.enrich([stored])
        result = rec.get(stored.record_id)

        self.assertEqual(enricher.direct_trace_failures, 1)
        self.assertEqual(result.reason, "un mouvement a été détecté")
        self.assertEqual(result.trigger["trace_backend"], "ha_mcp")
        self.assertEqual(len(protocol.calls), 2)
        self.assertEqual(protocol.calls[0][1]["automation_id"], "automation.hotte_mouvement")
        self.assertEqual(protocol.calls[0][1]["limit"], 3)
        self.assertEqual(protocol.calls[1][1]["run_id"], "run-mcp")
        rec.close()

    async def test_state_and_brightness_same_context_trigger_one_enrichment_run(self):
        old_delay = worker_module._DEBOUNCE_SECONDS
        worker_module._DEBOUNCE_SECONDS = 0.01
        rec = self.recorder()
        try:
            ha = FakeHA([self.automation_entry()])
            traces = FakeTraceInvestigator(motion_trace())
            worker = TargetedConsciousMemoryWorker(
                None, rec, DummyEnricher(ha, traces)
            )
            event = {
                "event_type": "state_changed",
                "time_fired": iso(2),
                "data": {
                    "entity_id": "light.hotte",
                    "old_state": {
                        "state": "off",
                        "attributes": {"friendly_name": "Hotte", "brightness": 0},
                    },
                    "new_state": {
                        "state": "on",
                        "attributes": {"friendly_name": "Hotte", "brightness": 180},
                        "context": {"id": "ctx-good", "parent_id": None, "user_id": None},
                    },
                },
                "context": {"id": "ctx-good", "parent_id": None, "user_id": None},
            }
            worker._capture_state(event)
            await asyncio.sleep(0.06)

            self.assertEqual(rec.count(), 2)
            self.assertEqual(worker.enrichment_runs, 1)
            self.assertEqual(worker.targeted.logbook_reads, 1)
            self.assertEqual(traces.calls, 1)
            primary = rec.find_best("light.hotte")
            brightness = rec.find_best("light.hotte", attribute="brightness")
            self.assertEqual(primary.reason, "un mouvement a été détecté")
            self.assertEqual(brightness.reason, "un mouvement a été détecté")
            status = worker.status()
            self.assertEqual(status["queue_capacity"], 0)
            self.assertEqual(status["enrichment_dropped"], 0)
            await worker.stop()
        finally:
            worker_module._DEBOUNCE_SECONDS = old_delay
            rec.close()


if __name__ == "__main__":
    unittest.main()
