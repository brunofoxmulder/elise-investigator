import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_enricher import CausalEnricher, initial_record, needs_enrichment
from causal_events import ObservedChange
from models import InvestigationResult


class FakeHA:
    async def get_state(self, entity_id):
        if entity_id == "binary_sensor.mouvement_entree":
            return {
                "entity_id": entity_id,
                "state": "off",
                "attributes": {
                    "friendly_name": "Mouvement entrée",
                    "device_class": "motion",
                },
            }
        return {"entity_id": entity_id, "state": "unknown", "attributes": {}}


class FakeInvestigator:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def investigate(self, request):
        self.calls += 1
        return self.result


def automation_result(trigger):
    return InvestigationResult(
        status="confirmed",
        entity_id="light.entree",
        entity_name="Lampe entrée",
        event_type="state_change",
        event_time="2026-08-28T10:00:00+00:00",
        observed={"before": "on", "after": "off", "attribute": None},
        cause={
            "type": "automation",
            "entity_id": "automation.entree",
            "name": "Gestion entrée",
            "system_confirmed": True,
        },
        chain=[
            {"kind": "trigger", "detail": trigger, "proven": True},
            {"kind": "automation", "entity_id": "automation.entree", "proven": True},
        ],
        evidence=[],
        meta={},
    )


def change(*, user_id=None):
    return ObservedChange(
        entity_id="light.entree",
        entity_name="Lampe entrée",
        event_time="2026-08-28T10:00:00+00:00",
        event_kind="turned_off",
        before_value="on",
        after_value="off",
        attribute=None,
        context_id="ctx",
        parent_id=None,
        user_id=user_id,
        domain="light",
    )


class TestCausalEnricher(unittest.IsolatedAsyncioTestCase):
    async def test_motion_trigger_becomes_functional_reason(self):
        result = automation_result(
            {
                "platform": "state",
                "entity_id": "binary_sensor.mouvement_entree",
                "to": "off",
            }
        )
        investigator = FakeInvestigator(result)
        enricher = CausalEnricher(investigator, FakeHA())
        item = initial_record(change())
        enriched = await enricher.enrich(change(), item)
        self.assertEqual(investigator.calls, 1)
        self.assertEqual(enriched.origin_type, "automation")
        self.assertEqual(enriched.confidence, "confirmed")
        self.assertEqual(enriched.reason, "il n'y avait plus de mouvement")
        self.assertEqual(enriched.source_entity_id, "automation.entree")
        self.assertNotIn("Gestion entrée", str(enriched.llm_payload()))

    async def test_time_pattern_is_not_invented_as_functional_reason(self):
        result = automation_result({"platform": "time_pattern", "minutes": "/10"})
        enricher = CausalEnricher(FakeInvestigator(result), FakeHA())
        enriched = await enricher.enrich(change(), initial_record(change()))
        self.assertEqual(enriched.origin_type, "automation")
        self.assertIsNone(enriched.reason)
        self.assertEqual(enriched.reason_code, "automation_trigger")

    async def test_direct_user_context_skips_expensive_investigation(self):
        investigator = FakeInvestigator(automation_result({"platform": "state"}))
        direct = change(user_id="user-123")
        self.assertFalse(needs_enrichment(direct))
        item = initial_record(direct)
        enriched = await CausalEnricher(investigator, FakeHA()).enrich(direct, item)
        self.assertEqual(investigator.calls, 0)
        self.assertEqual(enriched.origin_type, "user")
        self.assertEqual(enriched.confidence, "confirmed")

    async def test_sensor_changes_are_recorded_but_not_deep_enriched(self):
        sensor = ObservedChange(
            entity_id="sensor.temperature",
            entity_name="Température",
            event_time="2026-08-28T10:00:00+00:00",
            event_kind="state_changed",
            before_value="20",
            after_value="20.1",
            attribute=None,
            context_id=None,
            parent_id=None,
            user_id=None,
            domain="sensor",
        )
        self.assertFalse(needs_enrichment(sensor))


if __name__ == "__main__":
    unittest.main()
