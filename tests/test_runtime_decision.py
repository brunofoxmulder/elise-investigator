import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from models import Evidence, InvestigationResult
from runtime_decision import extract_runtime_decision


class TestRuntimeDecision(unittest.TestCase):
    def test_cover_target_uses_direct_sun_and_lux_dependencies(self):
        detail = {
            "config": {
                "variables": {
                    "temperature": "{{ states('sensor.temperature_exterieure') | float }}",
                    "azimut": "{{ states('sensor.sun_azimuth') | float }}",
                    "elevation": "{{ states('sensor.sun_elevation') | float }}",
                    "luminosite": "{{ states('sensor.illuminance_exterieure') | float }}",
                    "position_base": "{% if temperature > 28 %} 0 {% else %} 50 {% endif %}",
                    "position_corrigee": "{% if azimut > 54 and elevation > 0 and luminosite > 15000 %} {{ position_base - 10 }} {% else %} {{ position_base }} {% endif %}",
                },
                "action": [
                    {
                        "action": "cover.set_cover_position",
                        "target": {"entity_id": "cover.volet_salon_2"},
                        "data": {"position": "{{ position_corrigee }}"},
                    }
                ],
            },
            "trace": {
                "variables/0": [
                    {
                        "changed_variables": {
                            "temperature": 19.2,
                            "azimut": 139.5,
                            "elevation": 50.2,
                            "luminosite": 52000,
                            "position_base": 50,
                            "position_corrigee": 40,
                        }
                    }
                ],
                "action/0": [
                    {
                        "result": {
                            "params": {
                                "domain": "cover",
                                "service": "set_cover_position",
                                "target": {"entity_id": "cover.volet_salon_2"},
                                "service_data": {"position": 40},
                            }
                        }
                    }
                ],
            },
        }
        result = InvestigationResult(
            status="confirmed",
            entity_id="cover.volet_salon_2",
            entity_name="Volet salon",
            event_type="attribute_change",
            event_time="2026-08-28T10:00:00+00:00",
            observed={"before": 50, "after": 40, "attribute": "current_position"},
            cause={
                "type": "automation",
                "entity_id": "automation.volet_salon",
                "system_confirmed": True,
            },
            evidence=[Evidence(kind="trace", summary="trace", source="automation.volet_salon", raw=detail)],
        )

        decision = extract_runtime_decision(result)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.output_variable, "position_corrigee")
        self.assertEqual(decision.target_value, 40)
        self.assertIn("position du soleil", decision.reason)
        self.assertIn("luminosité", decision.reason)
        # Temperature is a transitive input through position_base; direct external
        # dependencies of the final correction are preferred when available.
        self.assertNotIn("température", decision.reason)
        factor_entities = {item["entity_id"] for item in decision.factors}
        self.assertIn("sensor.sun_azimuth", factor_entities)
        self.assertIn("sensor.sun_elevation", factor_entities)
        self.assertIn("sensor.illuminance_exterieure", factor_entities)
        self.assertNotIn("sensor.temperature_exterieure", factor_entities)

    def test_ambiguous_multiple_matching_commands_are_not_interpreted(self):
        detail = {
            "config": {"variables": {"target": "{{ states('sensor.x') | float }}"}},
            "trace": {
                "variables/0": [{"changed_variables": {"target": 40}}],
                "action/0": [{"result": {"params": {"domain": "cover", "service": "set_cover_position", "target": {"entity_id": "cover.test"}, "service_data": {"position": 40}}}}],
                "action/1": [{"result": {"params": {"domain": "cover", "service": "set_cover_position", "target": {"entity_id": "cover.test"}, "service_data": {"position": 40}}}}],
            },
        }
        result = InvestigationResult(
            status="confirmed",
            entity_id="cover.test",
            entity_name="Cover",
            event_type="attribute_change",
            event_time="2026-08-28T10:00:00+00:00",
            observed={"before": 50, "after": 40, "attribute": "current_position"},
            cause={"type": "automation", "entity_id": "automation.test", "system_confirmed": True},
            evidence=[Evidence(kind="trace", summary="trace", source="automation.test", raw=detail)],
        )
        self.assertIsNone(extract_runtime_decision(result))


if __name__ == "__main__":
    unittest.main()
