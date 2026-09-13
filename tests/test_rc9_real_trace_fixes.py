from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_renderer_rc9 import CausalRendererRC9
from causal_resolver_rc9 import resolve_cause_rc9, unique_effect_command_rc9
from models import Evidence, InvestigationResult


class _HA:
    async def get_state(self, entity_id: str):
        return {
            "entity_id": entity_id,
            "state": "0",
            "attributes": {
                "friendly_name": "Prise aspirateur Power" if entity_id.endswith("_power") else entity_id,
                "unit_of_measurement": "W" if entity_id.endswith("_power") else None,
            },
        }


def _device_runtime(domain: str, service: str, device_id: str) -> dict:
    return {
        "result": {
            "params": {
                "domain": domain,
                "service": service,
                "target": {"device_id": device_id},
            }
        }
    }


def _result(entity_id: str, before: str, after: str, trace: dict, source: str) -> InvestigationResult:
    result = InvestigationResult(
        status="confirmed",
        entity_id=entity_id,
        entity_name=entity_id,
        event_type="turned_off" if after == "off" else "turned_on",
        event_time="2026-09-13T21:00:27+00:00",
        observed={"before": before, "after": after, "attribute": None},
        cause={"type": "automation", "entity_id": source, "name": source, "system_confirmed": True},
        evidence=[Evidence(kind="trace", summary="trace", strength="direct", raw=trace)],
    )
    return result


class RC9RealTraceFixes(unittest.IsolatedAsyncioTestCase):
    def test_brosse_device_action_off_after_completed_delay(self):
        trace = {
            "config": {
                "actions": [
                    {"type": "turn_on", "domain": "switch", "device_id": "brush"},
                    {"delay": {"hours": 1, "seconds": 1}},
                    {"type": "turn_off", "domain": "switch", "device_id": "brush"},
                ]
            },
            "trace": {
                "action/0": [_device_runtime("switch", "turn_on", "brush")],
                "action/1": [{"result": {"delay": 3601, "done": True}}],
                "action/2": [_device_runtime("switch", "turn_off", "brush")],
            },
        }
        result = _result("switch.prise_brosse_a_dents", "on", "off", trace, "automation.charge_brosse_a_dents")
        command = unique_effect_command_rc9(result)
        self.assertIsNotNone(command)
        self.assertEqual(command.get("path"), "action/2")
        cause = resolve_cause_rc9(result)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "delay_elapsed")
        self.assertEqual(cause.get("detail", {}).get("delay_seconds"), 3601)

    async def test_aspirateur_default_branch_after_failed_power_condition(self):
        trace = {
            "config": {
                "actions": [
                    {"type": "turn_on", "domain": "switch", "device_id": "vacuum"},
                    {"delay": {"minutes": 2}},
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {
                                        "condition": "numeric_state",
                                        "entity_id": "sensor.prise_aspirateur_power",
                                        "above": 1,
                                    }
                                ],
                                "sequence": [
                                    {"wait_for_trigger": [{"trigger": "numeric_state", "entity_id": "sensor.prise_aspirateur_power", "below": 1, "for": {"minutes": 2}}]},
                                    {"type": "turn_off", "domain": "switch", "device_id": "vacuum"},
                                ],
                            }
                        ],
                        "default": [
                            {"type": "turn_off", "domain": "switch", "device_id": "vacuum"}
                        ],
                    },
                ]
            },
            "trace": {
                "action/0": [_device_runtime("switch", "turn_on", "vacuum")],
                "action/1": [{"result": {"delay": 120, "done": True}}],
                "action/2": [{"result": {"choice": "default"}}],
                "action/2/default/0": [_device_runtime("switch", "turn_off", "vacuum")],
            },
        }
        result = _result("switch.prise_aspirateur", "on", "off", trace, "automation.charge_aspirateur")
        cause = resolve_cause_rc9(result)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "choose_default_failed_condition")
        self.assertEqual(cause.get("detail", {}).get("prior_delay_seconds"), 120)
        renderer = CausalRendererRC9(_HA())
        text = await renderer.render(cause)
        self.assertEqual(
            text,
            "après le délai de 2 min, la condition « Prise aspirateur Power > 1 W » n'était pas satisfaite",
        )

    def test_explicit_other_entity_is_never_borrowed(self):
        trace = {
            "config": {"actions": [{"action": "switch.turn_off"}]},
            "trace": {
                "action/0": [
                    {
                        "result": {
                            "params": {
                                "domain": "switch",
                                "service": "turn_off",
                                "target": {"entity_id": "switch.autre_prise"},
                            }
                        }
                    }
                ]
            },
        }
        result = _result("switch.prise_brosse_a_dents", "on", "off", trace, "automation.test")
        self.assertIsNone(unique_effect_command_rc9(result))


if __name__ == "__main__":
    unittest.main()
