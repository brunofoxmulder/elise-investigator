from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecorder
from memory_worker_dev55 import TargetedConsciousMemoryWorker


BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=2)


def iso(seconds: float) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


def state_event(
    *,
    when: float,
    entity_id: str,
    before: str,
    after: str,
    context: str,
    parent: str | None = None,
    user_id: str | None = None,
) -> dict:
    return {
        "event_type": "state_changed",
        "time_fired": iso(when),
        "data": {
            "entity_id": entity_id,
            "old_state": {
                "state": before,
                "attributes": {"friendly_name": "Objet test"},
            },
            "new_state": {
                "state": after,
                "attributes": {"friendly_name": "Objet test"},
                "context": {"id": context, "parent_id": parent, "user_id": user_id},
            },
        },
    }


class DummyHA:
    pass


class DummyInvestigator:
    pass


class DummyEnricher:
    def __init__(self):
        self.ha = DummyHA()
        self.investigator = DummyInvestigator()


class TestDev55FunctionalEvents(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3")
        self.worker = TargetedConsciousMemoryWorker(
            None,
            self.recorder,
            enricher=DummyEnricher(),
        )
        # These tests isolate capture/selection.  They must not invoke HA reads.
        self.worker._schedule_episode = lambda key, records: None

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    async def test_on_unavailable_unknown_on_does_not_mask_real_turn_on(self):
        await self.worker._capture_event(
            state_event(
                when=0,
                entity_id="switch.test",
                before="off",
                after="on",
                context="user-on",
                user_id="user-1",
            )
        )
        await self.worker._capture_event(
            state_event(
                when=10,
                entity_id="switch.test",
                before="on",
                after="unavailable",
                context="lost",
            )
        )
        await self.worker._capture_event(
            state_event(
                when=11,
                entity_id="switch.test",
                before="unavailable",
                after="unknown",
                context="unknown",
            )
        )
        await self.worker._capture_event(
            state_event(
                when=12,
                entity_id="switch.test",
                before="unknown",
                after="on",
                context="recovered",
            )
        )

        rows = [row for row in self.recorder.for_entity("switch.test", limit=20) if row.attribute is None]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].event_kind, "turned_on")
        self.assertEqual(rows[0].origin_type, "user")
        self.assertEqual(rows[0].confidence, "confirmed")
        self.assertEqual(self.worker.technical_state_events_suppressed, 2)
        self.assertEqual(self.worker.availability_recoveries_suppressed, 1)

    async def test_off_unavailable_unknown_off_does_not_create_new_functional_event(self):
        await self.worker._capture_event(
            state_event(
                when=0,
                entity_id="light.test",
                before="on",
                after="off",
                context="user-off",
                user_id="user-1",
            )
        )
        for when, before, after in (
            (10, "off", "unavailable"),
            (11, "unavailable", "unknown"),
            (12, "unknown", "off"),
        ):
            await self.worker._capture_event(
                state_event(
                    when=when,
                    entity_id="light.test",
                    before=before,
                    after=after,
                    context=f"ctx-{when}",
                )
            )

        rows = [row for row in self.recorder.for_entity("light.test", limit=20) if row.attribute is None]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].event_kind, "turned_off")
        self.assertEqual(rows[0].origin_type, "user")

    async def test_recovery_to_different_state_is_kept_but_indeterminate(self):
        await self.worker._capture_event(
            state_event(
                when=0,
                entity_id="switch.test",
                before="off",
                after="on",
                context="user-on",
                user_id="user-1",
            )
        )
        await self.worker._capture_event(
            state_event(
                when=10,
                entity_id="switch.test",
                before="on",
                after="unavailable",
                context="lost",
            )
        )
        await self.worker._capture_event(
            state_event(
                when=11,
                entity_id="switch.test",
                before="unavailable",
                after="unknown",
                context="unknown",
            )
        )
        await self.worker._capture_event(
            state_event(
                when=12,
                entity_id="switch.test",
                before="unknown",
                after="off",
                context="recovered-off",
            )
        )

        rows = [row for row in self.recorder.for_entity("switch.test", limit=20) if row.attribute is None]
        self.assertEqual(len(rows), 2)
        newest = rows[0]
        self.assertEqual(newest.before_value, "on")
        self.assertEqual(newest.after_value, "off")
        self.assertEqual(newest.event_kind, "turned_off")
        self.assertEqual(newest.origin_type, "unknown")
        self.assertEqual(newest.confidence, "indeterminate")
        self.assertEqual(newest.reason_code, "availability_recovery_changed_functional_state")
        self.assertEqual(self.worker.availability_recoveries_changed, 1)

    async def test_unanchored_recovery_is_ignored_fail_closed(self):
        await self.worker._capture_event(
            state_event(
                when=0,
                entity_id="switch.test",
                before="unknown",
                after="on",
                context="recovered-after-restart",
            )
        )
        self.assertEqual(self.recorder.for_entity("switch.test", limit=20), [])
        self.assertEqual(self.worker.availability_recoveries_unanchored, 1)

    async def test_cover_states_bypass_binary_availability_filter(self):
        await self.worker._capture_event(
            state_event(
                when=0,
                entity_id="cover.test",
                before="open",
                after="closing",
                context="cover-closing",
            )
        )
        rows = [row for row in self.recorder.for_entity("cover.test", limit=20) if row.attribute is None]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].event_kind, "closing")

    async def test_status_exposes_native_first_strategy(self):
        status = self.worker.status()
        self.assertEqual(status["mode"], "native_ha_first_functional_memory")
        self.assertFalse(status["legacy_reverse_search_normal_path"])
        self.assertIn("native_context_logbook", status["causal_strategy"])


if __name__ == "__main__":
    unittest.main()
