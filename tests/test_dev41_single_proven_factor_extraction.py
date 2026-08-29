import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from proven_factor_extractor import attach_first_proven_factor


def record(*, reason="un mouvement a été détecté", proven=True, factors=None):
    return CausalRecord(
        entity_id="light.test",
        entity_name="Lampe test",
        event_time="2026-08-29T12:00:00+00:00",
        event_kind="turned_on",
        after_value="on",
        origin_type="automation",
        reason=reason,
        trigger={
            "human_cause": {
                "kind": "automation_trigger",
                "origin": "automation_trigger",
                "path": "trigger",
                "proven": proven,
                "detail": {"platform": "state", "entity_id": "binary_sensor.motion"},
            }
        },
        factors=factors,
        confidence="confirmed",
    )


class TestDev41SingleProvenFactorExtraction(unittest.TestCase):
    def test_proven_reason_becomes_one_structured_cause(self):
        item = record()
        self.assertTrue(attach_first_proven_factor(item))
        self.assertEqual(len(item.factors), 1)
        factor = item.factors[0]
        self.assertEqual(factor["role"], "cause")
        self.assertTrue(factor["proven"])
        self.assertEqual(factor["label"], "un mouvement a été détecté")
        self.assertEqual(factor["kind"], "automation_trigger")
        self.assertEqual(factor["proof_path"], "trigger")

    def test_existing_reason_is_not_modified(self):
        item = record(reason="la fenêtre a été ouverte")
        self.assertTrue(attach_first_proven_factor(item))
        self.assertEqual(item.reason, "la fenêtre a été ouverte")

    def test_unproven_human_cause_is_rejected(self):
        item = record(proven=False)
        self.assertFalse(attach_first_proven_factor(item))
        self.assertIsNone(item.factors)

    def test_missing_reason_is_rejected(self):
        item = record(reason=None)
        self.assertFalse(attach_first_proven_factor(item))
        self.assertIsNone(item.factors)

    def test_existing_factors_are_never_overwritten(self):
        existing = [{"kind": "state", "role": "cause", "proven": True, "label": "déjà présent"}]
        item = record(factors=existing)
        self.assertFalse(attach_first_proven_factor(item))
        self.assertEqual(item.factors, existing)

    def test_user_command_is_not_reclassified_as_factor(self):
        item = record()
        item.origin_type = "user"
        self.assertFalse(attach_first_proven_factor(item))
        self.assertIsNone(item.factors)


if __name__ == "__main__":
    unittest.main()
