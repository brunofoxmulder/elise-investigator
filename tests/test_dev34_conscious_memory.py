from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder_dev33 import RelevantCausalRecorder
from main_dev34 import _memory_payload
from memory_response_dev34 import answer_from_memory
from memory_worker_dev34 import ConsciousMemoryWorker
from models import InvestigationRequest
from request_journal_dev34 import RequestJournal


BASE = datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc)


def iso(offset: int = 0) -> str:
    return (BASE + timedelta(seconds=offset)).isoformat()


def automation_event(*, context_id: str, source: str, offset: int = 0) -> dict:
    return {
        "event_type": "automation_triggered",
        "time_fired": iso(offset),
        "data": {
            "entity_id": "automation.salle_de_bain",
            "name": "Salle de bain",
            "source": source,
        },
        "context": {"id": context_id, "parent_id": "trigger-parent", "user_id": None},
    }


def service_event(
    *,
    context_id: str,
    service: str = "turn_off",
    entity_id: str = "light.salle_de_bain",
    offset: int = 1,
) -> dict:
    return {
        "event_type": "call_service",
        "time_fired": iso(offset),
        "data": {
            "domain": "light",
            "service": service,
            "service_data": {"entity_id": entity_id},
        },
        "context": {"id": context_id, "parent_id": "trigger-parent", "user_id": None},
    }


def state_event(
    *,
    entity_id: str = "light.salle_de_bain",
    before: str = "on",
    after: str = "off",
    context_id: str = "ctx-1",
    user_id: str | None = None,
    offset: int = 2,
    old_attrs: dict | None = None,
    new_attrs: dict | None = None,
) -> dict:
    old_attributes = {"friendly_name": "Lampe salle de bain", **(old_attrs or {})}
    new_attributes = {"friendly_name": "Lampe salle de bain", **(new_attrs or {})}
    context = {"id": context_id, "parent_id": "trigger-parent", "user_id": user_id}
    return {
        "event_type": "state_changed",
        "time_fired": iso(offset),
        "data": {
            "entity_id": entity_id,
            "old_state": {
                "state": before,
                "attributes": old_attributes,
                "context": {"id": "old", "parent_id": None, "user_id": None},
            },
            "new_state": {
                "state": after,
                "attributes": new_attributes,
                "context": context,
            },
        },
        "context": context,
    }


class TestDev34ConsciousMemory(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def recorder(self) -> RelevantCausalRecorder:
        return RelevantCausalRecorder(self.root / "memory.sqlite3")

    async def test_actual_automation_command_is_remembered_without_deep_enrichment(self):
        recorder = self.recorder()

        class NeverCalledEnricher:
            async def enrich(self, *_args, **_kwargs):
                raise AssertionError("dev.34 must not deep-enrich the normal memory path")

        worker = ConsciousMemoryWorker(None, recorder, NeverCalledEnricher())
        await worker._capture_event(
            automation_event(
                context_id="ctx-1",
                source="state of binary_sensor.mouvement_sdb to off",
            )
        )
        await worker._capture_event(service_event(context_id="ctx-1"))
        await worker._capture_event(state_event(context_id="ctx-1"))

        record = recorder.latest("light.salle_de_bain")
        self.assertIsNotNone(record)
        self.assertEqual(record.before_value, "on")
        self.assertEqual(record.after_value, "off")
        self.assertEqual(record.origin_type, "automation")
        self.assertEqual(record.reason, "state of binary_sensor.mouvement_sdb to off")
        self.assertEqual(record.confidence, "confirmed")
        self.assertEqual(record.trigger["command"]["service"], "turn_off")
        self.assertEqual(worker.status()["queue_capacity"], 0)
        self.assertEqual(worker.records_written, 1)
        recorder.close()

    async def test_automation_evaluation_without_effect_does_not_clutter_memory(self):
        recorder = self.recorder()
        worker = ConsciousMemoryWorker(None, recorder)

        await worker._capture_event(
            automation_event(context_id="periodic", source="time pattern", offset=0)
        )

        self.assertEqual(recorder.count(), 0)
        self.assertEqual(worker.automation_events_seen, 1)
        recorder.close()

    async def test_generic_time_trigger_is_not_presented_as_functional_cause(self):
        recorder = self.recorder()
        worker = ConsciousMemoryWorker(None, recorder)

        await worker._capture_event(
            automation_event(context_id="periodic", source="time pattern", offset=0)
        )
        await worker._capture_event(
            {
                "event_type": "call_service",
                "time_fired": iso(1),
                "data": {
                    "domain": "cover",
                    "service": "set_cover_position",
                    "service_data": {
                        "entity_id": "cover.volet_salon_2",
                        "position": 40,
                    },
                },
                "context": {
                    "id": "periodic",
                    "parent_id": "trigger-parent",
                    "user_id": None,
                },
            }
        )
        await worker._capture_event(
            state_event(
                entity_id="cover.volet_salon_2",
                before="open",
                after="closing",
                context_id="periodic",
                offset=2,
                old_attrs={"current_position": 100},
                new_attrs={"current_position": 40},
            )
        )

        record = recorder.find_best("cover.volet_salon_2")
        self.assertIsNotNone(record)
        self.assertEqual(record.origin_type, "automation")
        self.assertIsNone(record.reason)
        self.assertEqual(answer_from_memory(record), "Je n'ai pas trouvé la cause.")
        recorder.close()

    async def test_direct_user_context_is_remembered_as_user_command(self):
        recorder = self.recorder()
        worker = ConsciousMemoryWorker(None, recorder)

        await worker._capture_event(
            state_event(context_id="user-ctx", user_id="user-id", offset=2)
        )

        record = recorder.latest("light.salle_de_bain")
        self.assertIsNotNone(record)
        self.assertEqual(record.origin_type, "user")
        self.assertEqual(record.confidence, "confirmed")
        self.assertIn(
            "commande utilisateur",
            answer_from_memory(record, now=BASE + timedelta(seconds=62)),
        )
        recorder.close()

    async def test_sensor_telemetry_is_not_duplicated_into_memory(self):
        recorder = self.recorder()
        worker = ConsciousMemoryWorker(None, recorder)

        await worker._capture_event(
            state_event(
                entity_id="sensor.temperature_exterieure",
                before="20",
                after="21",
                context_id="sensor",
            )
        )

        self.assertEqual(recorder.count(), 0)
        recorder.close()

    async def test_state_and_brightness_coexist_but_generic_lookup_prefers_state(self):
        recorder = self.recorder()
        worker = ConsciousMemoryWorker(None, recorder)

        await worker._capture_event(
            state_event(
                before="off",
                after="on",
                context_id="user-ctx",
                user_id="user-id",
                old_attrs={"brightness": 0},
                new_attrs={"brightness": 180},
            )
        )

        self.assertEqual(recorder.count(), 2)
        generic = recorder.find_best("light.salle_de_bain")
        brightness = recorder.find_best("light.salle_de_bain", attribute="brightness")
        self.assertIsNotNone(generic)
        self.assertIsNone(generic.attribute)
        self.assertEqual(generic.after_value, "on")
        self.assertIsNotNone(brightness)
        self.assertEqual(brightness.attribute, "brightness")
        self.assertEqual(brightness.after_value, 180)
        recorder.close()

    def test_memory_payload_is_always_confirmed_and_has_exact_fallback(self):
        recorder = self.recorder()
        app = {"causal_recorder": recorder}

        payload = _memory_payload(
            app, InvestigationRequest(entity_id="light.salle_de_bain")
        )

        self.assertEqual(payload["status"], "confirmed")
        self.assertIs(payload["cause_found"], False)
        self.assertEqual(payload["answer_text"], "Je n'ai pas trouvé la cause.")
        recorder.close()

    def test_request_journal_keeps_input_and_output_and_prunes(self):
        journal = RequestJournal(self.root / "requests.sqlite3", retention_hours=12)
        journal.append(
            "/api/v1/investigate",
            {"entity_id": "light.salle_de_bain"},
            {"status": "confirmed", "answer_text": "Je n'ai pas trouvé la cause."},
            now=BASE,
        )
        journal.append(
            "/api/v1/investigate",
            {"entity_id": "light.cuisine"},
            {"status": "confirmed", "answer_text": "ok"},
            now=BASE + timedelta(hours=13),
        )

        rows = journal.recent(limit=20)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["request"]["entity_id"], "light.cuisine")
        self.assertEqual(rows[0]["response"]["status"], "confirmed")
        journal.close()


if __name__ == "__main__":
    unittest.main()
