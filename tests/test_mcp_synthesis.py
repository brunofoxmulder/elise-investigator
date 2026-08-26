import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from mcp_synthesis import synthesize_mcp_findings


def _finding(tool, structured):
    return {
        "tool": tool,
        "success": True,
        "result": {"structuredContent": structured},
    }


class TestMCPLocalSynthesis(unittest.TestCase):
    def test_cover_closed_gets_natural_french_without_causal_verdict(self):
        findings = [
            _finding(
                "ha_get_state",
                {
                    "data": {
                        "entity_id": "cover.volet_salon_2",
                        "state": "closed",
                        "attributes": {
                            "friendly_name": "Volet salon",
                            "current_position": 0,
                        },
                    }
                },
            ),
            _finding(
                "ha_get_history",
                {
                    "data": {
                        "success": True,
                        "entities": [
                            {
                                "entity_id": "cover.volet_salon_2",
                                "states": [
                                    {
                                        "state": "closed",
                                        "last_changed": "2026-08-26T14:00:00+00:00",
                                        "attributes": {"current_position": 0},
                                    },
                                    {
                                        "state": "open",
                                        "last_changed": "2026-08-26T13:55:00+00:00",
                                        "attributes": {"current_position": 40},
                                    },
                                ],
                            }
                        ],
                    }
                },
            ),
            _finding(
                "ha_search",
                {
                    "data": {
                        "success": True,
                        "results": [
                            {
                                "entity_id": "automation.gestion_volet_salon",
                                "name": "Gestion volet salon avec soleil et saison",
                            }
                        ],
                    }
                },
            ),
        ]

        synthesis = synthesize_mcp_findings(
            "cover.volet_salon_2", "Pourquoi le volet salon est fermé ?", findings
        )

        self.assertIn("Volet salon est actuellement fermé (position 0 %)", synthesis["answer"])
        self.assertIn("passage de ouvert à 40 % à fermé", synthesis["answer"])
        self.assertIn("Gestion volet salon avec soleil et saison", synthesis["answer"])
        self.assertIn("pas une cause prouvée", synthesis["answer"])
        self.assertIsNone(synthesis["causal_verdict"])
        self.assertTrue(synthesis["investigator_status_unchanged"])
        self.assertFalse(synthesis["uses_llm"])
        self.assertEqual(synthesis["source"], "Recherche MCP locale")

    def test_light_state_is_readable(self):
        synthesis = synthesize_mcp_findings(
            "light.hotte",
            "État de la hotte",
            [
                _finding(
                    "ha_get_state",
                    {
                        "data": {
                            "entity_id": "light.hotte",
                            "state": "on",
                            "attributes": {"friendly_name": "hotte"},
                        }
                    },
                )
            ],
        )
        self.assertIn("hotte est actuellement allumé", synthesis["answer"])
        self.assertEqual(synthesis["status"], "observed")

    def test_empty_structured_data_stays_partial_and_does_not_guess(self):
        synthesis = synthesize_mcp_findings(
            "switch.unknown",
            "Pourquoi ?",
            [_finding("ha_get_state", {"data": {}})],
        )
        self.assertEqual(synthesis["status"], "partial")
        self.assertEqual(synthesis["facts"], [])
        self.assertEqual(synthesis["configuration_leads"], [])
        self.assertIsNone(synthesis["causal_verdict"])
        self.assertIn("pas fourni assez de données", synthesis["answer"])

    def test_no_investigator_certainty_is_emitted(self):
        synthesis = synthesize_mcp_findings(
            "cover.volet_salon_2",
            "Pourquoi ?",
            [_finding("ha_get_state", {"data": {"state": "closed"}})],
        )
        serialized = str(synthesis)
        self.assertNotIn("'causal_verdict': 'confirmed'", serialized)
        self.assertNotIn("'causal_verdict': 'probable'", serialized)
        self.assertNotIn("'causal_verdict': 'indeterminate'", serialized)
        self.assertIsNone(synthesis["causal_verdict"])


if __name__ == "__main__":
    unittest.main()
