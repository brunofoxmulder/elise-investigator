from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev62 import TargetedMemoryEnricher


class _HA:
    async def get_state(self, entity_id):
        if entity_id == "sensor.temperature_exterieure":
            return {
                "entity_id": entity_id,
                "state": "29.4",
                "attributes": {
                    "friendly_name": "Température extérieure",
                    "unit_of_measurement": "°C",
                },
            }
        return {"entity_id": entity_id, "attributes": {}}


class _TraceInvestigator:
    pass


def _detail(*, two_conditions: bool = False):
    conditions = [
        {
            "condition": "numeric_state",
            "entity_id": "sensor.temperature_exterieure",
            "above": 28,
        }
    ]
    if two_conditions:
        conditions.append({"condition": "state", "entity_id": "input_boolean.bruno_est_la", "state": "on"})

    return {
        "config": {
            "actions": [
                {
                    "choose": [
                        {
                            "conditions": conditions,
                            "sequence": [
                                {
                                    "action": "cover.close_cover",
                                    "target": {"entity_id": "cover.volet_salon_2"},
                                }
                            ],
                        }
                    ]
                }
            ]
        },
        "trace": {
            "trigger/0": [
                {
                    "timestamp": "2026-09-07T13:20:00.500000+00:00",
                    "changed_variables": {
                        "trigger": {"platform": "time_pattern"}
                    },
                }
            ],
            "action/0": [
                {
                    "timestamp": "2026-09-07T13:20:00.700000+00:00",
                    "result": {"choice": 0},
                }
            ],
            "action/0/choose/0": [
                {
                    "timestamp": "2026-09-07T13:20:00.710000+00:00",
                    "result": {"result": True},
                }
            ],
            "action/0/choose/0/conditions/0": [
                {
                    "timestamp": "2026-09-07T13:20:00.720000+00:00",
                    "result": {
                        "result": True,
                        "state": 29.4,
                        "wanted_state_above": 28,
                    },
                }
            ],
            "action/0/choose/0/sequence/0": [
                {
                    "timestamp": "2026-09-07T13:20:00.900000+00:00",
                    "result": {
                        "params": {
                            "domain": "cover",
                            "service": "close_cover",
                            "target": {"entity_id": ["cover.volet_salon_2"]},
                            "service_data": {},
                        }
                    },
                }
            ],
        },
    }


class TestDev62TraceBranchCondition(unittest.IsolatedAsyncioTestCase):
    async def test_true_temperature_branch_beats_time_pattern_trigger(self):
        helper = TargetedMemoryEnricher(_HA(), _TraceInvestigator())
        record = CausalRecord(
            entity_id="cover.volet_salon_2",
            event_time="2026-09-07T13:20:01+00:00",
            event_kind="closed",
            after_value="closed",
            origin_type="automation",
            source_entity_id="automation.gestion_volet_salon_avec_soleil_et_saison",
            source_name="Gestion volet salon avec soleil et saison",
            confidence="confirmed",
        )

        reason, run_id, cause = await helper._reason_from_detail(
            record,
            record.source_entity_id,
            record.source_name,
            "automation",
            _detail(),
            "run-temperature",
        )

        self.assertEqual(run_id, "run-temperature")
        self.assertEqual(reason, "la température extérieure dépassait 28 °C")
        self.assertEqual(cause["origin"], "choose_condition")
        self.assertEqual(cause["detail"]["entity_id"], "sensor.temperature_exterieure")
        self.assertEqual(cause["detail"]["above"], 28)
        self.assertTrue(cause["detail"]["condition_result"])

    async def test_multiple_branch_conditions_do_not_guess_one_business_cause(self):
        helper = TargetedMemoryEnricher(_HA(), _TraceInvestigator())
        record = CausalRecord(
            entity_id="cover.volet_salon_2",
            event_time="2026-09-07T13:20:01+00:00",
            event_kind="closed",
            after_value="closed",
            origin_type="automation",
            source_entity_id="automation.gestion_volet_salon_avec_soleil_et_saison",
            confidence="confirmed",
        )

        reason, _, cause = await helper._reason_from_detail(
            record,
            record.source_entity_id,
            None,
            "automation",
            _detail(two_conditions=True),
            "run-ambiguous",
        )

        self.assertIsNone(reason)
        self.assertEqual(cause["origin"], "automation_trigger")
        self.assertEqual(cause["detail"]["platform"], "time_pattern")


if __name__ == "__main__":
    unittest.main()
