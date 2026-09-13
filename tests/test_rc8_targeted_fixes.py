from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_renderer_v2 import CausalRendererV2
from causal_resolver_v2 import resolve_cause
from models import Evidence, InvestigationResult


class _HA:
    async def get_state(self, entity_id: str):
        names = {
            "binary_sensor.rte_tempo_heures_creuses": "RTE Tempo Heures Creuses",
            "sensor.prise_aspirateur_power": "Prise aspirateur Power",
        }
        return {"entity_id": entity_id, "state": "on", "attributes": {"friendly_name": names.get(entity_id, entity_id), "unit_of_measurement": "W" if entity_id.endswith("_power") else None}}


def _command(domain: str, service: str, target: str) -> dict:
    return {
        "result": {
            "params": {
                "domain": domain,
                "service": service,
                "target": {"entity_id": target},
            }
        }
    }


def _result(trace: dict) -> InvestigationResult:
    result = InvestigationResult(
        status="confirmed",
        entity_id="switch.prise_aspirateur",
        entity_name="Prise aspirateur",
        event_type="turned_off",
        event_time="2026-09-13T20:02:26+00:00",
        observed={"before": "on", "after": "off", "attribute": None},
        cause={
            "type": "automation",
            "entity_id": "automation.charge_aspirateur",
            "name": "Charge aspirateur",
            "system_confirmed": True,
        },
        evidence=[Evidence(kind="trace", summary="trace", strength="direct", raw=trace)],
    )
    result.chain.append(
        {
            "kind": "trigger",
            "detail": {
                "platform": "device",
                "type": "turned_on",
                "entity_id": "binary_sensor.rte_tempo_heures_creuses",
            },
            "proven": True,
        }
    )
    result.chain.append({"kind": "automation", "entity_id": "automation.charge_aspirateur", "proven": True})
    return result


class RC8TargetedFixes(unittest.IsolatedAsyncioTestCase):
    async def test_device_turned_on_trigger_is_rendered_without_to_state(self):
        renderer = CausalRendererV2(_HA())
        cause = {
            "kind": "automation_trigger",
            "origin": "automation_trigger",
            "proven": True,
            "detail": {
                "platform": "device",
                "type": "turned_on",
                "entity_id": "binary_sensor.rte_tempo_heures_creuses",
            },
        }
        text = await renderer.render(cause)
        self.assertEqual(text, "« RTE Tempo Heures Creuses » est passé à on")

    def test_nested_completed_wait_in_choose_sequence_releases_aspirateur_off(self):
        trace = {
            "config": {
                "actions": [
                    {"action": "switch.turn_on", "target": {"entity_id": "switch.prise_aspirateur"}},
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
                                    {
                                        "wait_for_trigger": [
                                            {
                                                "trigger": "numeric_state",
                                                "entity_id": "sensor.prise_aspirateur_power",
                                                "below": 1,
                                                "for": {"minutes": 2},
                                            }
                                        ]
                                    },
                                    {"action": "switch.turn_off", "target": {"entity_id": "switch.prise_aspirateur"}},
                                ],
                            }
                        ],
                        "default": [
                            {"action": "switch.turn_off", "target": {"entity_id": "switch.prise_aspirateur"}}
                        ],
                    },
                ]
            },
            "trace": {
                "trigger/0": [
                    {
                        "changed_variables": {
                            "trigger": {
                                "platform": "device",
                                "type": "turned_on",
                                "entity_id": "binary_sensor.rte_tempo_heures_creuses",
                            }
                        }
                    }
                ],
                "action/0": [_command("switch", "turn_on", "switch.prise_aspirateur")],
                "action/1": [{"result": {"done": True}}],
                "action/2/choose/0/sequence/0": [
                    {
                        "result": {
                            "wait": {
                                "completed": True,
                                "trigger": {
                                    "platform": "numeric_state",
                                    "entity_id": "sensor.prise_aspirateur_power",
                                    "below": 1,
                                    "idx": "0",
                                },
                            }
                        }
                    }
                ],
                "action/2/choose/0/sequence/1": [
                    _command("switch", "turn_off", "switch.prise_aspirateur")
                ],
            },
        }
        cause = resolve_cause(_result(trace))
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "wait_for_trigger")
        self.assertEqual(cause.get("path"), "action/2/choose/0/sequence/0")
        self.assertEqual(cause.get("command_path"), "action/2/choose/0/sequence/1")
        self.assertEqual(cause.get("detail", {}).get("entity_id"), "sensor.prise_aspirateur_power")
        self.assertEqual(cause.get("detail", {}).get("below"), 1)
        self.assertEqual(cause.get("detail", {}).get("for"), {"minutes": 2})


if __name__ == "__main__":
    unittest.main()
