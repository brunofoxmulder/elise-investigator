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
from targeted_memory_enricher_dev39 import TargetedMemoryEnricher

BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=10)
ENTITY = "cover.volet_salon_2"
AUTOMATION = "automation.gestion_volet_salon_avec_soleil_et_saison"
REASON = "la luminosité extérieure était faible malgré la position du soleil"


def iso(seconds: float = 0) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


class ExplodingHA:
    async def get_logbook(self, entity_id, start, end):
        raise AssertionError("valid cover continuity must not query terminal Logbook")


class EmptyTraceInvestigator:
    pass


class RecoveringEnricher(TargetedMemoryEnricher):
    def __init__(self, ha):
        super().__init__(ha, EmptyTraceInvestigator())
        self.recovery_calls = 0

    async def _trace_reason(self, record, source_entity_id, source_name, source_kind):
        self.recovery_calls += 1
        self.last_trace_backend = "test_targeted_trace"
        return (
            REASON,
            "fa4928b955c49f13fdddbd270185a19d",
            {
                "kind": "branch_decision",
                "origin": source_kind,
                "proven": True,
                "detail": {"actual": 12451, "below": 45000},
            },
        )


class ExplodingRecoveryEnricher(RecoveringEnricher):
    async def _trace_reason(self, record, source_entity_id, source_name, source_kind):
        raise AssertionError("an already materialized cause must not re-read the trace")


class TestDev39CoverEpisodeCausePropagation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3")

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    def _automatic_start(self, motion: str, *, reason=None) -> CausalRecord:
        return self.recorder.record(
            CausalRecord(
                entity_id=ENTITY,
                entity_name="Volet salon",
                event_time=iso(10),
                event_kind=motion,
                before_value="open" if motion == "closing" else "closed",
                after_value=motion,
                origin_type="automation",
                source_entity_id=AUTOMATION,
                source_name="Gestion volet salon avec soleil et saison",
                reason=reason,
                reason_code="automation_trigger_without_functional_reason" if reason is None else "test",
                trigger={
                    "automation_trigger": {"entity_id": AUTOMATION, "source": "time_pattern"},
                    "command": {
                        "domain": "cover",
                        "service": "set_cover_position",
                        "service_data": {"entity_id": ENTITY},
                    },
                },
                confidence="confirmed",
            )
        )

    def _user_start(self, motion: str) -> CausalRecord:
        return self.recorder.record(
            CausalRecord(
                entity_id=ENTITY,
                entity_name="Volet salon",
                event_time=iso(10),
                event_kind=motion,
                before_value="open" if motion == "closing" else "closed",
                after_value=motion,
                origin_type="user",
                reason_code="home_assistant_user_context",
                confidence="confirmed",
            )
        )

    def _terminal(self, before: str, after: str, *, seconds: float = 30) -> CausalRecord:
        return self.recorder.record(
            CausalRecord(
                entity_id=ENTITY,
                entity_name="Volet salon",
                event_time=iso(seconds),
                event_kind=after,
                before_value=before,
                after_value=after,
                origin_type="unknown",
                confidence="confirmed",
            )
        )

    def _position(self, before: int, after: int, *, seconds: float = 30) -> CausalRecord:
        return self.recorder.record(
            CausalRecord(
                entity_id=ENTITY,
                entity_name="Volet salon",
                event_time=iso(seconds),
                event_kind="attribute_changed",
                before_value=before,
                after_value=after,
                attribute="current_position",
                origin_type="unknown",
                confidence="confirmed",
            )
        )

    async def _assert_automatic_episode(self, motion, terminal, before_pos, after_pos):
        source = self._automatic_start(motion)
        end = self._terminal(motion, terminal)
        position = self._position(before_pos, after_pos)
        enricher = RecoveringEnricher(ExplodingHA()).bind_recorder(self.recorder)

        self.assertTrue(await enricher.enrich([end, position]))
        self.assertEqual(enricher.recovery_calls, 1)

        recovered_source = self.recorder.get(source.record_id)
        self.assertEqual(recovered_source.origin_type, "automation")
        self.assertEqual(recovered_source.reason, REASON)
        self.assertEqual(recovered_source.reason_code, "cover_episode_source_trace")

        for record_id in (end.record_id, position.record_id):
            result = self.recorder.get(record_id)
            self.assertEqual(result.origin_type, "automation")
            self.assertEqual(result.source_entity_id, AUTOMATION)
            self.assertEqual(result.reason, REASON)
            self.assertEqual(result.reason_code, "cover_episode_continuity")
            self.assertEqual(
                result.trace_run_id,
                "fa4928b955c49f13fdddbd270185a19d",
            )
            self.assertEqual(result.trigger["cover_episode"]["source_record_id"], source.record_id)

    async def test_automatic_complete_opening_recovers_cause_at_start(self):
        await self._assert_automatic_episode("opening", "open", 99, 100)

    async def test_automatic_partial_opening_recovers_cause_at_start(self):
        await self._assert_automatic_episode("opening", "open", 59, 60)

    async def test_automatic_partial_closing_recovers_cause_at_start(self):
        await self._assert_automatic_episode("closing", "open", 41, 40)

    async def test_automatic_complete_closing_recovers_cause_at_start(self):
        await self._assert_automatic_episode("closing", "closed", 1, 0)

    async def test_user_command_propagates_without_trace_lookup(self):
        source = self._user_start("closing")
        end = self._terminal("closing", "open")
        position = self._position(61, 60)
        enricher = ExplodingRecoveryEnricher(ExplodingHA()).bind_recorder(self.recorder)

        self.assertTrue(await enricher.enrich([end, position]))
        for record_id in (end.record_id, position.record_id):
            result = self.recorder.get(record_id)
            self.assertEqual(result.origin_type, "user")
            self.assertIsNone(result.reason)
            self.assertEqual(result.reason_code, "cover_episode_continuity")
            self.assertEqual(result.trigger["cover_episode"]["source_record_id"], source.record_id)

    async def test_existing_automatic_reason_is_preserved_without_trace_lookup(self):
        source = self._automatic_start("opening", reason="fenêtre ouverte")
        end = self._terminal("opening", "open")
        enricher = ExplodingRecoveryEnricher(ExplodingHA()).bind_recorder(self.recorder)

        self.assertTrue(await enricher.enrich([end]))
        result = self.recorder.get(end.record_id)
        self.assertEqual(result.reason, "fenêtre ouverte")
        self.assertEqual(result.trigger["cover_episode"]["source_record_id"], source.record_id)

    async def test_incoherent_opening_to_closed_is_still_rejected(self):
        self._automatic_start("opening")
        end = self._terminal("opening", "closed")
        enricher = RecoveringEnricher(ExplodingHA()).bind_recorder(self.recorder)

        with self.assertRaises(AssertionError):
            await enricher.enrich([end])
        self.assertEqual(enricher.recovery_calls, 0)

    async def test_non_cover_behavior_does_not_enter_episode_recovery(self):
        light = self.recorder.record(
            CausalRecord(
                entity_id="light.test",
                entity_name="Lampe test",
                event_time=iso(30),
                event_kind="on",
                before_value="off",
                after_value="on",
                origin_type="unknown",
                confidence="confirmed",
            )
        )
        enricher = RecoveringEnricher(ExplodingHA()).bind_recorder(self.recorder)

        with self.assertRaises(AssertionError):
            await enricher.enrich([light])
        self.assertEqual(enricher.recovery_calls, 0)


if __name__ == "__main__":
    unittest.main()
