from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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
    *, context_id: str, service: str = "turn_off", entity_id: str = "light.salle_de_bain", offset: int = 1
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


@pytest.mark.asyncio
async def test_actual_automation_command_is_remembered_without_deep_enrichment(tmp_path):
    recorder = RelevantCausalRecorder(tmp_path / "memory.sqlite3")

    class NeverCalledEnricher:
        async def enrich(self, *_args, **_kwargs):
            raise AssertionError("dev.34 must not deep-enrich the normal memory path")

    worker = ConsciousMemoryWorker(None, recorder, NeverCalledEnricher())
    await worker._capture_event(
        automation_event(context_id="ctx-1", source="state of binary_sensor.mouvement_sdb to off")
    )
    await worker._capture_event(service_event(context_id="ctx-1"))
    await worker._capture_event(state_event(context_id="ctx-1"))

    record = recorder.latest("light.salle_de_bain")
    assert record is not None
    assert record.before_value == "on"
    assert record.after_value == "off"
    assert record.origin_type == "automation"
    assert record.reason == "state of binary_sensor.mouvement_sdb to off"
    assert record.confidence == "confirmed"
    assert record.trigger["command"]["service"] == "turn_off"
    assert worker.status()["queue_capacity"] == 0
    assert worker.records_written == 1


@pytest.mark.asyncio
async def test_automation_evaluation_without_effect_does_not_clutter_memory(tmp_path):
    recorder = RelevantCausalRecorder(tmp_path / "memory.sqlite3")
    worker = ConsciousMemoryWorker(None, recorder)

    await worker._capture_event(
        automation_event(context_id="periodic", source="time pattern", offset=0)
    )

    assert recorder.count() == 0
    assert worker.automation_events_seen == 1


@pytest.mark.asyncio
async def test_generic_time_trigger_is_not_presented_as_functional_cause(tmp_path):
    recorder = RelevantCausalRecorder(tmp_path / "memory.sqlite3")
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
                "service_data": {"entity_id": "cover.volet_salon_2", "position": 40},
            },
            "context": {"id": "periodic", "parent_id": "trigger-parent", "user_id": None},
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
    assert record is not None
    assert record.origin_type == "automation"
    assert record.reason is None
    assert answer_from_memory(record) == "Je n'ai pas trouvé la cause."


@pytest.mark.asyncio
async def test_direct_user_context_is_remembered_as_user_command(tmp_path):
    recorder = RelevantCausalRecorder(tmp_path / "memory.sqlite3")
    worker = ConsciousMemoryWorker(None, recorder)

    await worker._capture_event(
        state_event(context_id="user-ctx", user_id="user-id", offset=2)
    )

    record = recorder.latest("light.salle_de_bain")
    assert record is not None
    assert record.origin_type == "user"
    assert record.confidence == "confirmed"
    assert "commande utilisateur" in answer_from_memory(record, now=BASE + timedelta(seconds=62))


@pytest.mark.asyncio
async def test_sensor_telemetry_is_not_duplicated_into_memory(tmp_path):
    recorder = RelevantCausalRecorder(tmp_path / "memory.sqlite3")
    worker = ConsciousMemoryWorker(None, recorder)

    await worker._capture_event(
        state_event(
            entity_id="sensor.temperature_exterieure",
            before="20",
            after="21",
            context_id="sensor",
        )
    )

    assert recorder.count() == 0


@pytest.mark.asyncio
async def test_state_and_brightness_can_coexist_but_generic_lookup_prefers_state(tmp_path):
    recorder = RelevantCausalRecorder(tmp_path / "memory.sqlite3")
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

    assert recorder.count() == 2
    generic = recorder.find_best("light.salle_de_bain")
    brightness = recorder.find_best("light.salle_de_bain", attribute="brightness")
    assert generic is not None and generic.attribute is None and generic.after_value == "on"
    assert brightness is not None and brightness.attribute == "brightness" and brightness.after_value == 180


def test_memory_payload_is_always_confirmed_and_has_exact_fallback(tmp_path):
    recorder = RelevantCausalRecorder(tmp_path / "memory.sqlite3")
    app = {"causal_recorder": recorder}

    payload = _memory_payload(app, InvestigationRequest(entity_id="light.salle_de_bain"))

    assert payload["status"] == "confirmed"
    assert payload["cause_found"] is False
    assert payload["answer_text"] == "Je n'ai pas trouvé la cause."


def test_request_journal_keeps_input_and_output_and_prunes(tmp_path):
    journal = RequestJournal(tmp_path / "requests.sqlite3", retention_hours=12)
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
    assert len(rows) == 1
    assert rows[0]["request"]["entity_id"] == "light.cuisine"
    assert rows[0]["response"]["status"] == "confirmed"
