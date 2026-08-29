import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from combined_trigger_condition_factors import combined_trigger_condition_factors


def phone_detail(*, branch=0, include_guard=False, target="switch.prise_intelligente_l4"):
    conditions = [
        {"condition": "state", "entity_id": "binary_sensor.rte_tempo_heures_creuses", "state": "on"}
    ]
    if include_guard:
        conditions.append({"condition": "state", "entity_id": "input_boolean.autorisation_charge", "state": "on"})
    config = {
        "triggers": [
            {"trigger": "state", "entity_id": "binary_sensor.rte_tempo_heures_creuses", "to": "on"},
            {"trigger": "numeric_state", "entity_id": "sensor.sm_s918b_battery_level", "below": 95},
            {"trigger": "numeric_state", "entity_id": "sensor.sm_s918b_battery_level", "above": 99},
        ],
        "conditions": conditions,
        "actions": [
            {
                "choose": [
                    {
                        "conditions": [
                            {"condition": "numeric_state", "entity_id": "sensor.sm_s918b_battery_level", "below": 95}
                        ],
                        "sequence": [
                            {"delay": "00:30:00"},
                            {"action": "switch.turn_on", "target": {"entity_id": target}},
                        ],
                    },
                    {
                        "conditions": [
                            {"condition": "numeric_state", "entity_id": "sensor.sm_s918b_battery_level", "above": 99}
                        ],
                        "sequence": [
                            {"action": "switch.turn_off", "target": {"entity_id": target}},
                        ],
                    },
                ]
            }
        ],
    }
    trace = {
        "condition/0": [{"result": {"result": True, "state": "on"}}],
    }
    if include_guard:
        trace["condition/1"] = [{"result": {"result": True, "state": "on"}}]
    if branch == 0:
        trace["action/0/choose/0/conditions/0"] = [{"result": {"result": True, "state": "72"}}]
    else:
        trace["action/0/choose/1/conditions/0"] = [{"result": {"result": True, "state": "100"}}]
    return {"config": config, "trace": trace}


class TestDev43TriggerConditionConjunction(unittest.TestCase):
    def test_phone_turn_on_yields_hc_and_low_battery(self):
        factors = combined_trigger_condition_factors(phone_detail(branch=0), "switch.prise_intelligente_l4")
        self.assertEqual(len(factors), 2)
        self.assertEqual(factors[0]["kind"], "state")
        self.assertEqual(factors[0]["relation"], "is")
        self.assertEqual(factors[0]["value"], "on")
        self.assertEqual(factors[1]["kind"], "numeric_state")
        self.assertEqual(factors[1]["relation"], "below")
        self.assertEqual(factors[1]["threshold"], 95)
        self.assertEqual(factors[1]["value"], "72")
        self.assertTrue(all(f["proven"] and f["role"] == "cause" for f in factors))

    def test_phone_turn_off_yields_hc_and_full_battery(self):
        factors = combined_trigger_condition_factors(phone_detail(branch=1), "switch.prise_intelligente_l4")
        self.assertEqual(len(factors), 2)
        self.assertEqual(factors[1]["relation"], "above")
        self.assertEqual(factors[1]["threshold"], 99)
        self.assertEqual(factors[1]["value"], "100")

    def test_true_guard_not_present_as_trigger_is_not_promoted(self):
        factors = combined_trigger_condition_factors(
            phone_detail(branch=0, include_guard=True), "switch.prise_intelligente_l4"
        )
        self.assertEqual(len(factors), 2)
        self.assertFalse(any(f.get("proof_entity_id") == "input_boolean.autorisation_charge" for f in factors))

    def test_wrong_target_branch_is_not_borrowed(self):
        detail = phone_detail(branch=0, target="switch.other")
        factors = combined_trigger_condition_factors(detail, "switch.prise_intelligente_l4")
        self.assertEqual(factors, [])

    def test_condition_not_runtime_true_is_not_promoted(self):
        detail = phone_detail(branch=0)
        detail["trace"]["action/0/choose/0/conditions/0"] = [{"result": {"result": False, "state": "96"}}]
        self.assertEqual(combined_trigger_condition_factors(detail, "switch.prise_intelligente_l4"), [])

    def test_single_trigger_automation_never_becomes_combined(self):
        detail = phone_detail(branch=0)
        detail["config"]["triggers"] = [detail["config"]["triggers"][0]]
        self.assertEqual(combined_trigger_condition_factors(detail, "switch.prise_intelligente_l4"), [])


if __name__ == "__main__":
    unittest.main()
