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
from memory_worker_dev54 import TargetedConsciousMemoryWorker


BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=2)


def iso(seconds: float) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


def satellite_state(*, when: float, state: str, context: str, parent: str | None = None) -> dict:
    return {
        "event_type": "state_changed",
        "time_fired": iso(when),
        "data": {
            "entity_id": "assist_satellite.home_assistant_voice_test_satellite_assist",
            "old_state": {"state": "idle", "attributes": {}},
            "new_state": {
                "state": state,
                "attributes": {"friendly_name": "Home Assistant Voice Test"},
                "context": {"id": context, "parent_id": parent, "user_id": None},
            },
        },
    }


def service_event(
    *,
    when: float,
    domain: str,
    service: str,
    entity_id: str,
    context: str,
    parent: str | None = None,
    user_id: str | None = None,
    extra: dict | None = None,
) -> dict:
    service_data = {"entity_id": entity_id, **(extra or {})}
    return {
        "event_type": "call_service",
        "time_fired": iso(when),
        "context": {"id": context, "parent_id": parent, "user_id": user_id},
        "data": {"domain": domain, "service": service, "service_data": service_data},
    }


def state_event(
    *,
    when: float,
    entity_id: str,
    before: str,
    after: str,
    context: str,
    parent: str | None = None,
    user_id: str | None = None,
    old_attrs: dict | None = None,
    new_attrs: dict | None = None,
) -> dict:
    name = "Volet salon" if entity_id.startswith("cover.") else "Lampe salon"
    return {
        "event_type": "state_changed",
        "time_fired": iso(when),
        "data": {
            "entity_id": entity_id,
            "old_state": {
                "state": before,
                "attributes": {"friendly_name": name, **(old_attrs or {})},
            },
            "new_state": {
                "state": after,
                "attributes": {"friendly_name": name, **(new_attrs or {})},
                "context": {"id": context, "parent_id": parent, "user_id": user_id},
            },
        },
    }


def automation_event(*, when: float, context: str, parent: str | None = None) -> dict:
    return {
        "event_type": "automation_triggered",
        "time_fired": iso(when),
        "context": {"id": context, "parent_id": parent, "user_id": None},
        "data": {
            "entity_id": "automation.volet_salon",
            "name": "Gestion volet salon",
            "source": "state of input_boolean.test to on",
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


class TestDev54AssistSatelliteUserOrigin(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3")
        self.worker = TargetedConsciousMemoryWorker(
            None,
            self.recorder,
            enricher=DummyEnricher(),
        )
        self.worker._schedule_episode = lambda key, records: None

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    async def _voice_session(self, *, base: float, suffix: str) -> tuple[str, str]:
        listening = f"voice-listening-{suffix}"
        processing = f"voice-processing-{suffix}"
        await self.worker._capture_event(
            satellite_state(when=base, state="listening", context=listening)
        )
        await self.worker._capture_event(
            satellite_state(
                when=base + 1,
                state="processing",
                context=processing,
                parent=listening,
            )
        )
        return listening, processing

    async def test_home_assistant_voice_command_is_same_generic_user_origin(self):
        _, processing = await self._voice_session(base=0, suffix="on")
        await self.worker._capture_event(
            service_event(
                when=2,
                domain="light",
                service="turn_on",
                entity_id="light.salon",
                context="voice-command-on",
                parent=processing,
            )
        )
        await self.worker._capture_event(
            state_event(
                when=3,
                entity_id="light.salon",
                before="off",
                after="on",
                context="effect-on",
                parent="voice-command-on",
            )
        )

        record = self.recorder.find_best("light.salon")
        self.assertIsNotNone(record)
        self.assertEqual(record.origin_type, "user")
        self.assertEqual(record.reason_code, "home_assistant_user_context")
        self.assertEqual(record.confidence, "confirmed")

    async def test_existing_user_id_command_is_unchanged(self):
        await self.worker._capture_event(
            state_event(
                when=2,
                entity_id="light.salon",
                before="off",
                after="on",
                context="existing-user",
                user_id="user-id",
            )
        )

        record = self.recorder.find_best("light.salon")
        self.assertIsNotNone(record)
        self.assertEqual(record.origin_type, "user")
        self.assertEqual(record.reason_code, "home_assistant_user_context")
        self.assertEqual(record.confidence, "confirmed")

    async def test_voice_light_off_on_and_on_off_are_both_user_commands(self):
        _, processing_on = await self._voice_session(base=0, suffix="on")
        await self.worker._capture_event(
            service_event(
                when=2,
                domain="light",
                service="turn_on",
                entity_id="light.salon",
                context="cmd-on",
                parent=processing_on,
            )
        )
        await self.worker._capture_event(
            state_event(
                when=3,
                entity_id="light.salon",
                before="off",
                after="on",
                context="effect-on",
                parent="cmd-on",
            )
        )

        _, processing_off = await self._voice_session(base=10, suffix="off")
        await self.worker._capture_event(
            service_event(
                when=12,
                domain="light",
                service="turn_off",
                entity_id="light.salon",
                context="cmd-off",
                parent=processing_off,
            )
        )
        await self.worker._capture_event(
            state_event(
                when=13,
                entity_id="light.salon",
                before="on",
                after="off",
                context="effect-off",
                parent="cmd-off",
            )
        )

        rows = self.recorder.recent(entity_id="light.salon", limit=10)
        primary = [row for row in rows if row.attribute is None]
        self.assertEqual(len(primary), 2)
        self.assertEqual({row.event_kind for row in primary}, {"turned_on", "turned_off"})
        self.assertTrue(all(row.origin_type == "user" for row in primary))
        self.assertTrue(
            all(row.reason_code == "home_assistant_user_context" for row in primary)
        )

    async def test_non_voice_unknown_context_stays_unknown(self):
        await self.worker._capture_event(
            service_event(
                when=2,
                domain="light",
                service="turn_on",
                entity_id="light.salon",
                context="not-voice-command",
            )
        )
        await self.worker._capture_event(
            state_event(
                when=3,
                entity_id="light.salon",
                before="off",
                after="on",
                context="not-voice-effect",
                parent="not-voice-command",
            )
        )

        record = self.recorder.find_best("light.salon")
        self.assertIsNotNone(record)
        self.assertEqual(record.origin_type, "unknown")

    async def test_voice_triggered_automation_is_not_relabelled_as_user(self):
        _, processing = await self._voice_session(base=0, suffix="automation")
        await self.worker._capture_event(
            automation_event(when=2, context="automation-run", parent=processing)
        )
        await self.worker._capture_event(
            service_event(
                when=3,
                domain="cover",
                service="set_cover_position",
                entity_id="cover.volet_salon_2",
                context="cover-command",
                parent="automation-run",
                extra={"position": 40},
            )
        )
        await self.worker._capture_event(
            state_event(
                when=4,
                entity_id="cover.volet_salon_2",
                before="open",
                after="closing",
                context="cover-effect",
                parent="cover-command",
                old_attrs={"current_position": 100},
                new_attrs={"current_position": 40},
            )
        )

        record = self.recorder.find_best("cover.volet_salon_2")
        self.assertIsNotNone(record)
        self.assertEqual(record.origin_type, "automation")
        self.assertEqual(record.source_entity_id, "automation.volet_salon")

    async def test_direct_voice_cover_command_uses_user_origin_without_cover_special_case(self):
        _, processing = await self._voice_session(base=0, suffix="cover")
        await self.worker._capture_event(
            service_event(
                when=2,
                domain="cover",
                service="set_cover_position",
                entity_id="cover.volet_salon_2",
                context="voice-cover-command",
                parent=processing,
                extra={"position": 50},
            )
        )
        await self.worker._capture_event(
            state_event(
                when=3,
                entity_id="cover.volet_salon_2",
                before="open",
                after="closing",
                context="voice-cover-effect",
                parent="voice-cover-command",
                old_attrs={"current_position": 100},
                new_attrs={"current_position": 50},
            )
        )

        record = self.recorder.find_best("cover.volet_salon_2")
        self.assertIsNotNone(record)
        self.assertEqual(record.origin_type, "user")
        self.assertEqual(record.reason_code, "home_assistant_user_context")


if __name__ == "__main__":
    unittest.main()
