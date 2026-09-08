from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_dev63 import _linked_native_attribution
from models import Evidence, InvestigationResult
from trace_final_action_dev63 import select_chosen_branch_conditions, select_wait_timeout_cause


def _result(entity_id: str, after: str, detail: dict) -> InvestigationResult:
    return InvestigationResult(
        status="confirmed",
        entity_id=entity_id,
        entity_name=entity_id,
        event_type="state_changed",
        event_time="2026-09-08T12:00:05+00:00",
        observed={"before": None, "after": after, "attribute": None},
        cause={
            "type": "automation",
            "entity_id": "automation.test",
            "name": "Test",
            "system_confirmed": True,
        },
        evidence=[Evidence(kind="trace", summary="trace", source="automation.test", strength="direct", raw=detail)],
    )


class TestDev63FinalAction(unittest.TestCase):
    def test_wait_timeout_immediately_before_switch_off_is_cause(self):
        detail = {
            "config": {
                "actions": [
                    {"action": "switch.turn_on", "target": {"entity_id": "switch.evier"}},
                    {
                        "wait_for_trigger": [
                            {"trigger": "numeric_state", "entity_id": "sensor.evier_power", "below": 0.5, "for": "00:05:00"}
                        ],
                        "timeout": "04:00:00",
                        "continue_on_timeout": True,
                    },
                    {"action": "switch.turn_off", "target": {"entity_id": "switch.evier"}},
                ]
            },
            "trace": {
                "action/0": [{"result": {"params": {"domain": "switch", "service": "turn_on", "target": {"entity_id": "switch.evier"}}}}],
                "action/1": [{"result": {"wait": {"completed": False, "trigger": None}}}],
                "action/2": [{"result": {"params": {"domain": "switch", "service": "turn_off", "target": {"entity_id": "switch.evier"}}}}],
            },
        }
        cause = select_wait_timeout_cause(_result("switch.evier", "off", detail))
        self.assertIsNotNone(cause)
        self.assertEqual(cause["origin"], "wait_timeout")
        self.assertEqual(cause["detail"]["timeout_seconds"], 14400)

    def test_selected_branch_keeps_two_proven_conditions(self):
        detail = {
            "config": {
                "actions": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {"condition": "state", "entity_id": "binary_sensor.heures_creuses", "state": "on"},
                                    {"condition": "numeric_state", "entity_id": "sensor.batterie", "below": 40},
                                ],
                                "sequence": [
                                    {"action": "switch.turn_on", "target": {"entity_id": "switch.telephone"}}
                                ],
                            }
                        ]
                    }
                ]
            },
            "trace": {
                "action/0": [{"result": {"choice": 0}}],
                "action/0/choose/0": [{"result": {"result": True}}],
                "action/0/choose/0/conditions/0": [{"result": {"result": True, "state": "on"}}],
                "action/0/choose/0/conditions/1": [{"result": {"result": True, "state": "32"}}],
                "action/0/choose/0/sequence/0": [
                    {
                        "timestamp": "2026-09-08T12:00:04+00:00",
                        "result": {"params": {"domain": "switch", "service": "turn_on", "target": {"entity_id": "switch.telephone"}}},
                    }
                ],
            },
        }
        cause = select_chosen_branch_conditions(_result("switch.telephone", "on", detail))
        self.assertIsNotNone(cause)
        self.assertEqual(cause["origin"], "choose_conditions")
        self.assertEqual(len(cause["detail"]["conditions"]), 2)
        self.assertEqual(cause["detail"]["conditions"][1]["below"], 40)

    def test_activity_attribution_can_live_on_linked_non_state_row(self):
        fact = {"entity_id": "switch.yaourtiere", "state": "off", "context_id": "ctx-action"}
        current = fact
        activity_row = {
            "entity_id": "automation.aaaayaourt",
            "context_parent_id": "ctx-action",
            "context_entity_id": "automation.aaaayaourt",
            "context_entity_id_name": "Aaaayaourt",
        }
        selected = _linked_native_attribution(fact, current, [fact, activity_row])
        self.assertIs(selected, activity_row)


if __name__ == "__main__":
    unittest.main()
