import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_factors import public_causal_factors, structured_factor


class TestDev40StructuredFactorsContract(unittest.TestCase):
    def test_two_proven_causes_are_exposed_in_order(self):
        factors = [
            structured_factor(
                kind="state",
                role="cause",
                proven=True,
                label="Heures creuses",
                relation="active",
                value=True,
                entity_id="binary_sensor.heures_creuses",
                trace_path="action/0/conditions/0",
            ),
            structured_factor(
                kind="numeric_state",
                role="cause",
                proven=True,
                label="Batterie téléphone",
                relation="below",
                value=35,
                threshold=80,
                unit="%",
                entity_id="sensor.telephone_battery",
                trace_path="action/0/conditions/1",
            ),
        ]

        self.assertEqual(
            public_causal_factors(factors),
            [
                {
                    "kind": "state",
                    "role": "cause",
                    "label": "Heures creuses",
                    "relation": "active",
                    "value": True,
                },
                {
                    "kind": "numeric_state",
                    "role": "cause",
                    "label": "Batterie téléphone",
                    "relation": "below",
                    "value": 35,
                    "threshold": 80,
                    "unit": "%",
                },
            ],
        )

    def test_preconditions_and_guards_are_not_promoted_to_causes(self):
        factors = [
            structured_factor(
                kind="state",
                role="precondition",
                proven=True,
                label="Climatisation",
                relation="equals",
                value="cool",
            ),
            structured_factor(
                kind="state",
                role="guard",
                proven=True,
                label="Fenêtre",
                relation="closed",
                value=True,
            ),
        ]
        self.assertEqual(public_causal_factors(factors), [])

    def test_unproven_factor_never_reaches_language_layer(self):
        factor = structured_factor(
            kind="numeric_state",
            role="cause",
            proven=False,
            label="Luminosité extérieure",
            relation="below",
            value=12451,
            threshold=45000,
            unit="lx",
        )
        self.assertEqual(public_causal_factors([factor]), [])

    def test_optional_business_metadata_does_not_replace_proof(self):
        proven = structured_factor(
            kind="numeric_state",
            role="cause",
            proven=True,
            label="Luminosité extérieure",
            relation="below",
            value=12451,
            threshold=45000,
            unit="lx",
            business_label="protection solaire non nécessaire",
        )
        unproven = structured_factor(
            kind="numeric_state",
            role="cause",
            proven=False,
            label="Luminosité extérieure",
            relation="below",
            value=12451,
            threshold=45000,
            unit="lx",
            business_label="protection solaire non nécessaire",
        )

        self.assertEqual(
            public_causal_factors([proven]),
            [
                {
                    "kind": "numeric_state",
                    "role": "cause",
                    "label": "Luminosité extérieure",
                    "relation": "below",
                    "value": 12451,
                    "threshold": 45000,
                    "unit": "lx",
                    "business_label": "protection solaire non nécessaire",
                }
            ],
        )
        self.assertEqual(public_causal_factors([unproven]), [])

    def test_private_proof_fields_are_never_exposed(self):
        factor = structured_factor(
            kind="state",
            role="cause",
            proven=True,
            label="Heures creuses",
            relation="active",
            value=True,
            entity_id="binary_sensor.secret",
            automation_id="automation.secret",
            trace_run_id="secret-run",
            trace_path="action/4/choose/0",
            raw_trigger={"platform": "state"},
        )
        text = str(public_causal_factors([factor]))
        self.assertNotIn("binary_sensor.secret", text)
        self.assertNotIn("automation.secret", text)
        self.assertNotIn("secret-run", text)
        self.assertNotIn("action/4", text)
        self.assertNotIn("raw_trigger", text)


if __name__ == "__main__":
    unittest.main()
