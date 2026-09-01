from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from causal_recorder_dev49 import LatestPrimaryStateRecorder
from targeted_memory_enricher_dev49 import TargetedMemoryEnricher


class ReplayRecorder(LatestPrimaryStateRecorder):
    """In-memory recorder used to replay observed HA event sequences."""

    def __init__(self, records):
        self._records = list(records)

    def for_entity(self, entity_id, limit=100):
        return [r for r in self._records if r.entity_id == entity_id][:limit]


def event(
    record_id: int,
    entity_id: str,
    when: str,
    before: str,
    after: str,
    *,
    origin_type: str = "unknown",
    source_entity_id: str | None = None,
) -> CausalRecord:
    return CausalRecord(
        record_id=record_id,
        entity_id=entity_id,
        entity_name=entity_id,
        event_time=when,
        event_kind="turned_on" if after == "on" else "turned_off",
        before_value=before,
        after_value=after,
        attribute=None,
        origin_type=origin_type,
        source_entity_id=source_entity_id,
        source_name=source_entity_id,
        reason=None,
        confidence="confirmed",
    )


class TestObservedFieldReplay(unittest.TestCase):
    def _assert_recovery_noise_is_ignored(self, entity_id: str, real_before: str, real_after: str):
        real = event(
            1,
            entity_id,
            "2026-09-01T18:30:00+00:00",
            real_before,
            real_after,
            origin_type="automation",
            source_entity_id="automation.real_source",
        )
        unavailable = event(
            2,
            entity_id,
            "2026-09-01T19:34:03+00:00",
            real_after,
            "unavailable",
        )
        recovered = event(
            3,
            entity_id,
            "2026-09-01T19:34:07+00:00",
            "unavailable",
            real_after,
        )
        recorder = ReplayRecorder([recovered, unavailable, real])
        chosen = recorder.find_best(entity_id)
        self.assertIs(chosen, real)
        self.assertEqual((chosen.before_value, chosen.after_value), (real_before, real_after))

    def test_tineco_reconnect_does_not_replace_real_transition(self):
        self._assert_recovery_noise_is_ignored("switch.0xa4c1387da600c253", "on", "off")

    def test_phone_charger_reconnect_does_not_replace_real_transition(self):
        self._assert_recovery_noise_is_ignored("switch.chargeur_telephone_2", "off", "on")

    def test_yogurt_maker_reconnect_does_not_replace_real_transition(self):
        self._assert_recovery_noise_is_ignored("switch.yaourtiere", "off", "on")

    def test_aspirator_real_off_event_remains_context_linked_to_automation(self):
        aspirator = event(
            10,
            "switch.prise_aspirateur",
            "2026-09-01T20:08:09+00:00",
            "on",
            "off",
            origin_type="automation",
            source_entity_id="automation.charge_aspirateur",
        )
        self.assertTrue(
            TargetedMemoryEnricher._context_link_proven(
                aspirator,
                "automation.charge_aspirateur",
                "automation",
            )
        )

    def test_cover_is_not_eligible_for_generic_context_fallback(self):
        cover = event(
            20,
            "cover.volet_salon_2",
            "2026-09-01T18:00:00+00:00",
            "closing",
            "closed",
            origin_type="automation",
            source_entity_id="automation.gestion_volet_salon",
        )
        self.assertFalse(
            TargetedMemoryEnricher._context_link_proven(
                cover,
                "automation.gestion_volet_salon",
                "automation",
            )
        )


if __name__ == "__main__":
    unittest.main()
