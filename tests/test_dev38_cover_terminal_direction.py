from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord, CausalRecorder
from targeted_memory_enricher_dev38 import TargetedMemoryEnricher

# Keep simulated cover episodes recent enough to exercise the same 12 h rolling
# memory policy used on the HA deployment, without tying the suite to a calendar day.
BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=10)
ENTITY = "cover.volet_terrasse_2"


def iso(seconds: float = 0) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


class ExplodingHA:
    async def get_logbook(self, entity_id, start, end):
        raise AssertionError("valid cover continuity must not query Logbook")


class EmptyHA:
    async def get_logbook(self, entity_id, start, end):
        return []


class FakeTraceInvestigator:
    pass


class TestDev38CoverTerminalDirection(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3")

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    def _start(self, motion: str, reason: str = "position du soleil") -> CausalRecord:
        return self.recorder.record(
            CausalRecord(
                entity_id=ENTITY,
                entity_name="Volet terrasse",
                event_time=iso(10),
                event_kind=motion,
                before_value="open" if motion == "closing" else "closed",
                after_value=motion,
                origin_type="automation",
                source_entity_id="automation.gestion_volet_terrasse",
                source_name="Gestion volet terrasse",
                reason=reason,
                confidence="confirmed",
                trace_run_id="run-cover",
            )
        )

    def _terminal(self, before: str, after: str) -> CausalRecord:
        return self.recorder.record(
            CausalRecord(
                entity_id=ENTITY,
                entity_name="Volet terrasse",
                event_time=iso(20),
                event_kind=after,
                before_value=before,
                after_value=after,
                origin_type="unknown",
                confidence="confirmed",
            )
        )

    async def test_partial_closing_terminal_open_keeps_closing_cause(self):
        source = self._start("closing")
        terminal = self._terminal("closing", "open")
        enricher = TargetedMemoryEnricher(ExplodingHA(), FakeTraceInvestigator()).bind_recorder(
            self.recorder
        )

        self.assertTrue(await enricher.enrich([terminal]))
        result = self.recorder.get(terminal.record_id)
        self.assertEqual(result.origin_type, "automation")
        self.assertEqual(result.reason, "position du soleil")
        self.assertEqual(result.reason_code, "cover_episode_continuity")
        self.assertEqual(result.trigger["cover_episode"]["source_record_id"], source.record_id)
        self.assertEqual(result.trigger["cover_episode"]["source_after"], "closing")
        self.assertEqual(result.trigger["cover_episode"]["terminal_after"], "open")

    async def test_full_closing_terminal_closed_is_preserved(self):
        self._start("closing")
        terminal = self._terminal("closing", "closed")
        enricher = TargetedMemoryEnricher(ExplodingHA(), FakeTraceInvestigator()).bind_recorder(
            self.recorder
        )

        self.assertTrue(await enricher.enrich([terminal]))
        result = self.recorder.get(terminal.record_id)
        self.assertEqual(result.reason, "position du soleil")
        self.assertEqual(result.trace_run_id, "run-cover")

    async def test_opening_terminal_open_is_preserved(self):
        self._start("opening", reason="réouverture autorisée")
        terminal = self._terminal("opening", "open")
        enricher = TargetedMemoryEnricher(ExplodingHA(), FakeTraceInvestigator()).bind_recorder(
            self.recorder
        )

        self.assertTrue(await enricher.enrich([terminal]))
        result = self.recorder.get(terminal.record_id)
        self.assertEqual(result.reason, "réouverture autorisée")
        self.assertEqual(result.trace_run_id, "run-cover")

    async def test_incoherent_opening_to_closed_is_rejected(self):
        self._start("opening")
        terminal = self._terminal("opening", "closed")
        enricher = TargetedMemoryEnricher(EmptyHA(), FakeTraceInvestigator()).bind_recorder(
            self.recorder
        )

        self.assertFalse(await enricher.enrich([terminal]))
        result = self.recorder.get(terminal.record_id)
        self.assertEqual(result.origin_type, "unknown")
        self.assertIsNone(result.reason)

    async def test_terminal_cause_is_propagated_to_current_position(self):
        source = self._start("closing")
        terminal = self._terminal("closing", "open")
        position = self.recorder.record(
            CausalRecord(
                entity_id=ENTITY,
                entity_name="Volet terrasse",
                event_time=iso(20),
                event_kind="attribute_changed",
                before_value=100,
                after_value=40,
                attribute="current_position",
                origin_type="unknown",
                confidence="confirmed",
            )
        )
        enricher = TargetedMemoryEnricher(ExplodingHA(), FakeTraceInvestigator()).bind_recorder(
            self.recorder
        )

        self.assertTrue(await enricher.enrich([terminal, position]))
        for record_id in (terminal.record_id, position.record_id):
            result = self.recorder.get(record_id)
            self.assertEqual(result.origin_type, "automation")
            self.assertEqual(result.reason, "position du soleil")
            self.assertEqual(result.reason_code, "cover_episode_continuity")
            self.assertEqual(result.trigger["cover_episode"]["source_record_id"], source.record_id)


if __name__ == "__main__":
    unittest.main()
