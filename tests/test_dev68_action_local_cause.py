from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from models import Evidence, InvestigationResult
from trace_action_local_dev68 import (
    select_completed_wait_cause,
    select_elapsed_delay_cause,
    select_trigger_with_true_conditions,
)


def _result(entity_id: str, after: str, detail: dict, chain=None) -> InvestigationResult:
    result = InvestigationResult(
        status="confirmed",
        entity_id=entity_id,
        entity_name=entity_id,
        event_type="state_changed",
        event_time="2026-09-09T10:00:00+00:00",
        observed={"before": None, "after": after, "attribute": None},
        cause={"type": "automation", "entity_id": "automation.test", "name": "Test", "system_confirmed": True},
        evidence=[Evidence(kind="trace", summary="trace", source="automation.test", strength="direct", raw=detail)],
    )
    if chain is not None:
        result.chain = chain
    return result


class Dev68ActionLocalTests(unittest.TestCase):
    def test_single_target_command_after_completed_wait_is_enough(self):
        detail = {
            "config": {"actions": [
                {"wait_for_trigger": [{"trigger": "numeric_state", "entity_id": "sensor.power", "below": 1, "for": "00:05:00"}]},
                {"action": "switch.turn_off", "target": {"entity_id": "switch.aspirateur"}},
            ]},
            "trace": {
                "action/0": [{"result": {"wait": {"completed": True, "trigger": {"platform": "numeric_state", "entity_id": "sensor.power", "below": 1}}}}],
                "action/1": [{"result": {"params": {"domain": "switch", "service": "turn_off", "target": {"entity_id": "switch.aspirateur"}}}}],
            },
        }
        cause = select_completed_wait_cause(_result("switch.aspirateur", "off", detail))
        self.assertIsNotNone(cause)
        self.assertEqual(cause["origin"], "wait_for_trigger")
        self.assertEqual(cause["detail"]["entity_id"], "sensor.power")

    def test_executed_delay_immediately_before_off_beats_start_trigger(self):
        detail = {
            "config": {"actions": [
                {"delay": "04:00:00"},
                {"action": "switch.turn_off", "target": {"entity_id": "switch.brosse"}},
            ]},
            "trace": {
                "action/0": [{"result": {"result": True}}],
                "action/1": [{"result": {"params": {"domain": "switch", "service": "turn_off", "target": {"entity_id": "switch.brosse"}}}}],
            },
        }
        cause = select_elapsed_delay_cause(_result("switch.brosse", "off", detail))
        self.assertIsNotNone(cause)
        self.assertEqual(cause["origin"], "delay_elapsed")
        self.assertEqual(cause["detail"]["delay_seconds"], 14400)

    def test_start_trigger_and_true_top_level_condition_are_jointly_required(self):
        detail = {
            "config": {
                "conditions": [{"condition": "numeric_state", "entity_id": "sensor.battery", "below": 40}],
                "actions": [{"action": "switch.turn_on", "target": {"entity_id": "switch.telephone"}}],
            },
            "trace": {
                "condition/0": [{"result": {"result": True, "state": "32"}}],
                "action/0": [{"result": {"params": {"domain": "switch", "service": "turn_on", "target": {"entity_id": "switch.telephone"}}}}],
            },
        }
        chain = [{"kind": "trigger", "proven": True, "detail": {"platform": "state", "entity_id": "binary_sensor.heures_creuses", "to": "on"}}]
        cause = select_trigger_with_true_conditions(_result("switch.telephone", "on", detail, chain=chain))
        self.assertIsNotNone(cause)
        self.assertEqual(cause["origin"], "trigger_plus_conditions")
        self.assertEqual(cause["detail"]["conditions"][0]["below"], 40)


if __name__ == "__main__":
    unittest.main()
