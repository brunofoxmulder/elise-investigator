from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from causal_recorder_dev49 import LatestPrimaryStateRecorder
from targeted_memory_enricher_dev48 import TargetedMemoryEnricher as Dev48TargetedMemoryEnricher
from targeted_memory_enricher_dev49 import TargetedMemoryEnricher


def record(
    record_id,
    *,
    entity_id="switch.test",
    before="off",
    after="on",
    attribute=None,
    origin_type="automation",
    source_entity_id="automation.test",
):
    return CausalRecord(
        record_id=record_id,
        entity_id=entity_id,
        entity_name=entity_id,
        event_time=f"2026-09-01T20:00:0{record_id}+00:00",
        event_kind="turned_on" if after == "on" else "turned_off",
        before_value=before,
        after_value=after,
        attribute=attribute,
        origin_type=origin_type,
        source_entity_id=source_entity_id,
        source_name="Test",
        reason=None,
        confidence="confirmed",
    )


class FakeRecorder(LatestPrimaryStateRecorder):
    def __init__(self, records):
        self._records = list(records)

    def for_entity(self, entity_id, limit=100):
        return [r for r in self._records if r.entity_id == entity_id][:limit]


class TestDev49PrimarySelection(unittest.TestCase):
    def test_unavailable_recovery_never_hides_last_real_transition(self):
        recovered = record(3, before="unavailable", after="on")
        real = record(2, before="off", after="on")
        recorder = FakeRecorder([recovered, real])

        chosen = recorder.find_best("switch.test")

        self.assertIs(chosen, real)

    def test_unknown_recovery_never_hides_last_real_transition(self):
        recovered = record(3, before="unknown", after="off")
        real = record(2, before="on", after="off")
        recorder = FakeRecorder([recovered, real])

        chosen = recorder.find_best("switch.test")

        self.assertIs(chosen, real)

    def test_only_recovery_noise_returns_no_false_primary_event(self):
        recorder = FakeRecorder([record(3, before="unavailable", after="on")])
        self.assertIsNone(recorder.find_best("switch.test"))

    def test_cover_path_is_delegated_unchanged(self):
        cover = record(
            3,
            entity_id="cover.volet_salon_2",
            before="closing",
            after="closed",
        )
        recorder = FakeRecorder([cover])
        with patch.object(
            Dev48TargetedMemoryEnricher,
            "_context_link_proven",
            create=True,
        ):
            # Selection itself must still take the inherited cover path.
            self.assertIs(recorder.find_best("cover.volet_salon_2"), cover)


class TestDev49ContextLinkedReason(unittest.IsolatedAsyncioTestCase):
    async def test_context_linked_device_action_can_recover_human_reason(self):
        event = record(1)
        enricher = object.__new__(TargetedMemoryEnricher)
        enricher._label_cause = AsyncMock()

        cause = {
            "kind": "wait_for_trigger",
            "origin": "trace",
            "path": "action/2/choose/0/sequence/0",
            "proven": True,
            "detail": {
                "entity_id": "sensor.prise_aspirateur_power",
                "below": 1,
                "for": {"minutes": 2},
            },
        }

        with patch.object(
            Dev48TargetedMemoryEnricher,
            "_reason_from_detail",
            new=AsyncMock(return_value=(None, "run-1", None)),
        ), patch(
            "targeted_memory_enricher_dev49.complete_confirmed_trace_chain"
        ), patch(
            "targeted_memory_enricher_dev49.select_effect_linked_cause",
            return_value=cause,
        ), patch(
            "targeted_memory_enricher_dev49.human_cause_text",
            return_value="la puissance est restée sous 1 W pendant 2 minutes",
        ):
            text, run_id, compact = await enricher._reason_from_detail(
                event,
                "automation.test",
                "Charge aspirateur",
                "automation",
                {"trace": {}},
                "run-1",
            )

        self.assertEqual(text, "la puissance est restée sous 1 W pendant 2 minutes")
        self.assertEqual(run_id, "run-1")
        self.assertIsNotNone(compact)

    async def test_cover_never_uses_context_link_fallback(self):
        event = record(
            1,
            entity_id="cover.volet_salon_2",
            before="closing",
            after="closed",
        )
        self.assertFalse(
            TargetedMemoryEnricher._context_link_proven(
                event, "automation.test", "automation"
            )
        )


if __name__ == "__main__":
    unittest.main()
