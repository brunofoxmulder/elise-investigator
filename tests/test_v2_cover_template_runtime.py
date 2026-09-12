from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_renderer_v2 import CausalRendererV2
from cover_cause_v2 import cover_runtime_template_inputs, periodic_position_decision
from models import Evidence, InvestigationResult


class _HA:
    async def get_state(self, entity_id):
        return {"entity_id": entity_id, "attributes": {}}


def _result(detail, *, entity_id="cover.volet_salon_2"):
    return InvestigationResult(
        status="confirmed",
        entity_id=entity_id,
        entity_name="volet salon",
        event_type="opened",
        event_time="2026-09-12T13:40:05+00:00",
        observed={"after": "open"},
        cause={"type": "automation", "system_confirmed": True},
        evidence=[Evidence(kind="trace", summary="trace", source="automation.test", strength="direct", raw=detail)],
    )


class CoverRuntimeTemplateTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_style_variables_feed_periodic_cover_reason(self):
        detail = {
            "config": {
                "actions": [
                    {"choose": []},
                    {
                        "variables": {
                            "temperature": "{{ states('sensor.temperature_exterieure_fiable') | float(0) }}",
                            "azimut": "{{ states('sensor.sun_solar_azimuth') | float(999) }}",
                            "elevation": "{{ states('sensor.sun_solar_elevation') | float(0) }}",
                            "luminosite": "{{ states('sensor.lumiere_soleil_illuminance') | float(0) }}",
                            "position_volet_brut": "{% if temperature > 25 %}80{% else %}100{% endif %}",
                            "position_corrigee": "{{ position_volet_brut }}",
                        }
                    },
                    {"data": {"message": "debug"}},
                    {"condition": "template", "value_template": "{{ ecart >= 5 }}"},
                    {
                        "action": "cover.set_cover_position",
                        "target": {"entity_id": "cover.volet_salon_2"},
                        "data": {"position": "{{ position_corrigee | int(0) }}"},
                    },
                ]
            },
            "trace": {
                "action/1": [
                    {
                        "changed_variables": {
                            "temperature": 26.7,
                            "azimut": 171.3,
                            "elevation": 42.1,
                            "luminosite": 12340,
                            "position_volet_brut": 80,
                            "position_corrigee": 80,
                            "position_actuelle": 90,
                        }
                    }
                ],
                "action/4": [
                    {
                        "result": {
                            "params": {
                                "domain": "cover",
                                "service": "set_cover_position",
                                "target": {"entity_id": ["cover.volet_salon_2"]},
                                "service_data": {"position": 80},
                            }
                        }
                    }
                ],
            },
        }
        result = _result(detail)
        command = {
            "path": "action/4",
            "domain": "cover",
            "service": "set_cover_position",
            "data": {"position": 80},
        }
        inputs = cover_runtime_template_inputs(result, command)
        self.assertEqual(inputs["temperature"], 26.7)
        self.assertEqual(inputs["azimuth"], 171.3)
        self.assertEqual(inputs["elevation"], 42.1)
        self.assertEqual(inputs["lux"], 12340)
        self.assertEqual(inputs["raw_position"], 80)
        self.assertEqual(inputs["corrected_position"], 80)

        cause = periodic_position_decision(
            result,
            command,
            {"platform": "time_pattern", "minutes": "/10"},
        )
        text = await CausalRendererV2(_HA()).render(cause)
        self.assertIn("température 26.7 °C", text)
        self.assertIn("azimut 171.3°", text)
        self.assertIn("élévation 42.1°", text)
        self.assertIn("luminosité 12340 lx", text)
        self.assertIn("position 80 %", text)

    def test_runtime_snapshot_is_rejected_when_calculated_position_disagrees(self):
        detail = {
            "config": {
                "actions": [
                    {"variables": {"temperature": "x", "position_corrigee": "x"}},
                    {"action": "cover.set_cover_position"},
                ]
            },
            "trace": {
                "action/0": [{"changed_variables": {"temperature": 27, "position_corrigee": 30}}],
            },
        }
        result = _result(detail)
        command = {
            "path": "action/1",
            "domain": "cover",
            "service": "set_cover_position",
            "data": {"position": 80},
        }
        self.assertEqual(cover_runtime_template_inputs(result, command), {})

    def test_non_cover_never_uses_template_runtime_extension(self):
        detail = {
            "config": {"actions": [{"variables": {"temperature": "x"}}, {}]},
            "trace": {"action/0": [{"changed_variables": {"temperature": 27}}]},
        }
        result = _result(detail, entity_id="switch.test")
        command = {
            "path": "action/1",
            "domain": "switch",
            "service": "turn_on",
            "data": {},
        }
        self.assertEqual(cover_runtime_template_inputs(result, command), {})


if __name__ == "__main__":
    unittest.main()
