import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from proven_factor_extractor import factor_from_proven_human_cause


class TestDev42RichProvenFactorDetails(unittest.TestCase):
    def test_failed_above_condition_keeps_actual_and_boundary(self):
        factor = factor_from_proven_human_cause(
            "la luminosité ne dépassait pas 45 000 lx",
            {
                "kind": "branch_decision",
                "origin": "choose_default",
                "proven": True,
                "unit": "lx",
                "detail": {
                    "platform": "numeric_state",
                    "entity_id": "sensor.lux",
                    "above": 45000,
                    "actual": 12451,
                    "condition_result": False,
                },
            },
        )
        self.assertIsNotNone(factor)
        self.assertEqual(factor["relation"], "not_above")
        self.assertEqual(factor["value"], 12451)
        self.assertEqual(factor["threshold"], 45000)
        self.assertEqual(factor["unit"], "lx")
        self.assertTrue(factor["proven"])
        self.assertEqual(factor["role"], "cause")

    def test_failed_below_condition_is_symmetric(self):
        factor = factor_from_proven_human_cause(
            "la température n'était pas sous le seuil",
            {
                "kind": "branch_decision",
                "proven": True,
                "unit": "°C",
                "detail": {
                    "platform": "numeric_state",
                    "below": 18,
                    "actual": 21.2,
                    "condition_result": False,
                },
            },
        )
        self.assertEqual(factor["relation"], "not_below")
        self.assertEqual(factor["value"], 21.2)
        self.assertEqual(factor["threshold"], 18)

    def test_two_sided_false_condition_uses_runtime_value_only_when_decidable(self):
        low = factor_from_proven_human_cause(
            "hors plage basse",
            {
                "kind": "branch_decision",
                "proven": True,
                "detail": {
                    "platform": "numeric_state",
                    "above": 20,
                    "below": 30,
                    "actual": 18,
                    "condition_result": False,
                },
            },
        )
        high = factor_from_proven_human_cause(
            "hors plage haute",
            {
                "kind": "branch_decision",
                "proven": True,
                "detail": {
                    "platform": "numeric_state",
                    "above": 20,
                    "below": 30,
                    "actual": 31,
                    "condition_result": False,
                },
            },
        )
        self.assertEqual((low["relation"], low["threshold"]), ("not_above", 20))
        self.assertEqual((high["relation"], high["threshold"]), ("not_below", 30))

    def test_state_false_condition_keeps_actual_and_expected_state(self):
        factor = factor_from_proven_human_cause(
            "la fenêtre n'était pas fermée",
            {
                "kind": "branch_decision",
                "proven": True,
                "detail": {
                    "platform": "state",
                    "to": "off",
                    "actual": "on",
                    "condition_result": False,
                },
            },
        )
        self.assertEqual(factor["relation"], "not_equal")
        self.assertEqual(factor["value"], "on")
        self.assertEqual(factor["threshold"], "off")

    def test_state_trigger_keeps_change_target_without_inventing_condition_result(self):
        factor = factor_from_proven_human_cause(
            "la fenêtre a été ouverte",
            {
                "kind": "automation_trigger",
                "proven": True,
                "detail": {
                    "platform": "state",
                    "from": "off",
                    "to": "on",
                    "for": {"minutes": 5},
                },
            },
        )
        self.assertEqual(factor["relation"], "changed_to")
        self.assertEqual(factor["value"], "on")
        self.assertEqual(factor["duration"], "minutes=5")

    def test_unproven_factor_is_still_rejected(self):
        self.assertIsNone(
            factor_from_proven_human_cause(
                "texte",
                {
                    "kind": "branch_decision",
                    "proven": False,
                    "detail": {"platform": "numeric_state", "above": 10, "actual": 5},
                },
            )
        )

    def test_ambiguous_two_sided_false_condition_does_not_guess_boundary(self):
        factor = factor_from_proven_human_cause(
            "condition non satisfaite",
            {
                "kind": "branch_decision",
                "proven": True,
                "detail": {
                    "platform": "numeric_state",
                    "above": 20,
                    "below": 30,
                    "actual": "unknown",
                    "condition_result": False,
                },
            },
        )
        self.assertNotIn("relation", factor)
        self.assertNotIn("threshold", factor)
        self.assertEqual(factor["value"], "unknown")


if __name__ == "__main__":
    unittest.main()
