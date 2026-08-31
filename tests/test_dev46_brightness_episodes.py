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
from memory_worker_dev46 import TargetedConsciousMemoryWorker


BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=2)


def iso(seconds: float) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


def automation_event(*, when: float, context: str, entity_id: str, name: str, source: str) -> dict:
    return {
        "event_type": "automation_triggered",
        "time_fired": iso(when),
        "context": {"id": context, "parent_id": None, "user_id": None},
        "data": {"entity_id": entity_id, "name": name, "source": source},
    }


def light_service(
    *,
    when: float,
    context: str,
    parent: str | None = None,
    user_id: str | None = None,
    entity_id: str | None = "light.salon",
    brightness: int | None = None,
    transition: float | None = None,
) -> dict:
    service_data = {}
    if entity_id is not None:
        service_data["entity_id"] = entity_id
    if brightness is not None:
        service_data["brightness"] = brightness
    if transition is not None:
        service_data["transition"] = transition
    return {
        "event_type": "call_service",
        "time_fired": iso(when),
        "context": {"id": context, "parent_id": parent, "user_id": user_id},
        "data": {
            "domain": "light",
            "service": "turn_on",
            "service_data": service_data,
        },
    }


def light_state(
    *,
    when: float,
    before_state: str = "on",
    after_state: str = "on",
    before_brightness: int | None,
    after_brightness: int | None,
    context: str | None = None,
    parent: str | None = None,
    user_id: str | None = None,
) -> dict:
    return {
        "event_type": "state_changed",
        "time_fired": iso(when),
        "data": {
            "entity_id": "light.salon",
            "old_state": {
                "state": before_state,
                "attributes": {"friendly_name": "Lampe salon", "brightness": before_brightness},
            },
            "new_state": {
                "state": after_state,
                "attributes": {"friendly_name": "Lampe salon", "brightness": after_brightness},
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


class TestDev46BrightnessEpisodes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3")
        self.worker = TargetedConsciousMemoryWorker(
            None,
            self.recorder,
            enricher=DummyEnricher(),
        )
        # These tests exercise the direct event-memory proof and dev.46 episode
        # propagation, not the later targeted trace enrichment path.
        self.worker._schedule_episode = lambda key, records: None

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    async def _start_sunset_transition(self, *, transition: float = 30.0) -> None:
        await self.worker._capture_event(
            automation_event(
                when=0,
                context="auto-sunset",
                entity_id="automation.ambiance_soir",
                name="Ambiance du soir",
                source="sunset with offset -0:30:00",
            )
        )
        await self.worker._capture_event(
            light_service(
                when=1,
                context="cmd-sunset",
                parent="auto-sunset",
                brightness=255,
                transition=transition,
            )
        )
        await self.worker._capture_event(
            light_state(
                when=2,
                before_state="off",
                after_state="on",
                before_brightness=None,
                after_brightness=20,
                context="effect-start",
                parent="cmd-sunset",
            )
        )

    def _brightness_records(self):
        return [
            item
            for item in self.recorder.for_entity("light.salon", limit=50)
            if item.attribute == "brightness"
        ]

    async def test_normal_progressive_transition_keeps_initial_automation_cause(self):
        await self._start_sunset_transition()
        await self.worker._capture_event(
            light_state(
                when=8,
                before_brightness=20,
                after_brightness=80,
            )
        )

        latest = self._brightness_records()[0]
        self.assertEqual(latest.origin_type, "automation")
        self.assertEqual(latest.source_entity_id, "automation.ambiance_soir")
        self.assertIn("sunset", latest.reason)
        self.assertTrue(latest.reason_code.startswith("brightness_episode_inherited:"))
        self.assertEqual(self.worker.brightness_episode_inherited, 1)

    async def test_multiple_brightness_updates_inherit_same_initial_cause(self):
        await self._start_sunset_transition()
        for when, before, after in ((6, 20, 60), (12, 60, 120), (20, 120, 220)):
            await self.worker._capture_event(
                light_state(
                    when=when,
                    before_brightness=before,
                    after_brightness=after,
                )
            )

        records = self._brightness_records()
        inherited = [item for item in records if item.reason_code and item.reason_code.startswith("brightness_episode_inherited:")]
        self.assertEqual(len(inherited), 3)
        self.assertTrue(all(item.source_entity_id == "automation.ambiance_soir" for item in inherited))

    async def test_user_command_during_ramp_breaks_old_episode_and_becomes_new_cause(self):
        await self._start_sunset_transition()
        await self.worker._capture_event(
            light_state(when=7, before_brightness=20, after_brightness=70)
        )

        await self.worker._capture_event(
            light_service(
                when=10,
                context="cmd-user",
                user_id="user-1",
                brightness=100,
                transition=None,
            )
        )
        await self.worker._capture_event(
            light_state(
                when=11,
                before_brightness=70,
                after_brightness=100,
                context="effect-user",
                parent="cmd-user",
            )
        )
        user_record = self._brightness_records()[0]
        self.assertEqual(user_record.origin_type, "user")
        self.assertEqual(user_record.reason_code, "home_assistant_user_context")

        await self.worker._capture_event(
            light_state(when=14, before_brightness=100, after_brightness=130)
        )
        latest = self._brightness_records()[0]
        self.assertEqual(latest.origin_type, "unknown")
        self.assertIsNone(latest.reason)
        self.assertNotIn("light.salon", self.worker._brightness_transitions)

    async def test_user_command_with_transition_starts_new_user_episode(self):
        await self._start_sunset_transition()
        await self.worker._capture_event(
            light_service(
                when=10,
                context="cmd-user",
                user_id="user-1",
                brightness=180,
                transition=20,
            )
        )
        await self.worker._capture_event(
            light_state(
                when=11,
                before_brightness=20,
                after_brightness=90,
                context="effect-user",
                parent="cmd-user",
            )
        )
        await self.worker._capture_event(
            light_state(when=16, before_brightness=90, after_brightness=140)
        )

        latest = self._brightness_records()[0]
        self.assertEqual(latest.origin_type, "user")
        self.assertTrue(latest.reason_code.startswith("brightness_episode_inherited:"))

    async def test_other_automation_command_breaks_old_episode_and_new_transition_wins(self):
        await self._start_sunset_transition()
        await self.worker._capture_event(
            automation_event(
                when=10,
                context="auto-scene",
                entity_id="automation.mode_cinema",
                name="Mode cinéma",
                source="state of input_boolean.mode_cinema",
            )
        )
        await self.worker._capture_event(
            light_service(
                when=11,
                context="cmd-scene",
                parent="auto-scene",
                brightness=80,
                transition=15,
            )
        )
        await self.worker._capture_event(
            light_state(
                when=12,
                before_brightness=20,
                after_brightness=50,
                context="effect-scene",
                parent="cmd-scene",
            )
        )
        await self.worker._capture_event(
            light_state(when=16, before_brightness=50, after_brightness=70)
        )

        latest = self._brightness_records()[0]
        self.assertEqual(latest.origin_type, "automation")
        self.assertEqual(latest.source_entity_id, "automation.mode_cinema")
        self.assertIn("input_boolean.mode_cinema", latest.reason)
        self.assertNotEqual(latest.source_entity_id, "automation.ambiance_soir")

    async def test_no_explicit_transition_never_creates_temporal_only_episode(self):
        await self.worker._capture_event(
            automation_event(
                when=0,
                context="auto-plain",
                entity_id="automation.plain",
                name="Plain",
                source="state of binary_sensor.motion",
            )
        )
        await self.worker._capture_event(
            light_service(
                when=1,
                context="cmd-plain",
                parent="auto-plain",
                brightness=200,
                transition=None,
            )
        )
        await self.worker._capture_event(
            light_state(
                when=2,
                before_state="off",
                after_state="on",
                before_brightness=None,
                after_brightness=40,
                context="effect-plain",
                parent="cmd-plain",
            )
        )
        await self.worker._capture_event(
            light_state(when=6, before_brightness=40, after_brightness=90)
        )

        latest = self._brightness_records()[0]
        self.assertEqual(latest.origin_type, "unknown")
        self.assertNotIn("light.salon", self.worker._brightness_transitions)

    async def test_direction_reversal_breaks_episode_fail_closed(self):
        await self._start_sunset_transition()
        await self.worker._capture_event(
            light_state(when=6, before_brightness=20, after_brightness=70)
        )
        await self.worker._capture_event(
            light_state(when=10, before_brightness=70, after_brightness=55)
        )

        latest = self._brightness_records()[0]
        self.assertEqual(latest.origin_type, "unknown")
        self.assertIsNone(latest.reason)
        self.assertNotIn("light.salon", self.worker._brightness_transitions)
        self.assertGreaterEqual(self.worker.brightness_episode_rejected, 1)

    async def test_ambiguous_light_command_clears_active_episode(self):
        await self._start_sunset_transition()
        self.assertIn("light.salon", self.worker._brightness_transitions)

        # No explicit entity id: this represents an area/device-targeted light
        # command that cannot safely be assigned to one active transition.
        await self.worker._capture_event(
            light_service(
                when=8,
                context="cmd-area",
                entity_id=None,
                brightness=100,
            )
        )

        self.assertNotIn("light.salon", self.worker._brightness_transitions)
        self.assertGreaterEqual(self.worker.brightness_episode_breaks, 1)


if __name__ == "__main__":
    unittest.main()
