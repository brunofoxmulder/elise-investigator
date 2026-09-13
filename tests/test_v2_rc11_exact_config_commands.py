from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_rc11 import ActivityTraceReaderRC11
from causal_recorder import CausalRecord
from causal_resolver_rc11 import resolve_cause_rc11, unique_effect_command_rc11
from main_v2_rc11 import _answer_with_event_age
from models import Evidence, InvestigationResult


TARGET = "switch.prise_aspirateur"
CHILD_LOCK = "switch.prise_aspirateur_child_lock"
DEVICE_ID = "298492d607417ba93e8eb4f9705f67e9"
TARGET_REGISTRY_ID = "fdfd96fbb480c8f425b7d90f45a23460"
CHILD_REGISTRY_ID = "child-lock-registry-id"
REGISTRY = {
    "id": TARGET_REGISTRY_ID,
    "entity_id": TARGET,
    "device_id": DEVICE_ID,
    "unique_id": "0xa4c1380097d5ffff_switch_zigbee2mqtt",
    "platform": "mqtt",
}


def _device_action(action_type: str, *, entity_ref: str = TARGET_REGISTRY_ID) -> dict:
    return {
        "type": action_type,
        "device_id": DEVICE_ID,
        "entity_id": entity_ref,
        "domain": "switch",
    }


def _runtime(domain: str, service: str, target: dict) -> dict:
    return {
        "result": {
            "params": {
                "domain": domain,
                "service": service,
                "target": target,
            }
        }
    }


def _result(detail: dict, *, entity_id: str = TARGET, after: str = "off") -> InvestigationResult:
    return InvestigationResult(
        status="confirmed",
        entity_id=entity_id,
        entity_name=entity_id,
        event_type="turned_off" if after == "off" else "turned_on",
        event_time="2026-09-13T21:02:27+00:00",
        observed={"before": "on" if after == "off" else "off", "after": after, "attribute": None},
        cause={
            "type": "automation",
            "entity_id": "automation.charge_aspirateur",
            "name": "Charge aspirateur",
            "system_confirmed": True,
        },
        evidence=[Evidence(kind="trace", summary="trace", strength="direct", raw=detail)],
    )


def _terrain_default_trace(*, entity_ref: str = TARGET_REGISTRY_ID) -> dict:
    return {
        "config": {
            "action": [
                _device_action("turn_on", entity_ref=entity_ref),
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
                                _device_action("turn_off", entity_ref=entity_ref),
                            ],
                        }
                    ],
                    "default": [_device_action("turn_off", entity_ref=entity_ref)],
                },
            ]
        },
        "trace": {
            "action/0": [{"timestamp": "2026-09-13T21:00:27+00:00"}],
            "action/1": [
                {
                    "timestamp": "2026-09-13T21:00:27+00:00",
                    "result": {"delay": 120, "done": True},
                }
            ],
            "action/2": [
                {
                    "timestamp": "2026-09-13T21:02:27+00:00",
                    "result": {"choice": "default"},
                }
            ],
            "action/2/choose/0/conditions/0": [
                {"result": {"result": False, "state": "0"}}
            ],
            "action/2/default/0": [
                {"timestamp": "2026-09-13T21:02:27+00:00"}
            ],
        },
    }


class RC11ExactConfigCommandTests(unittest.IsolatedAsyncioTestCase):
    def test_terrain_default_branch_without_result_params_is_resolved(self):
        detail = _terrain_default_trace()
        original = deepcopy(detail)
        result = _result(detail)

        command = unique_effect_command_rc11(result, REGISTRY)
        self.assertIsNotNone(command)
        self.assertEqual(command.get("path"), "action/2/default/0")
        cause = resolve_cause_rc11(result, REGISTRY)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "choose_default_failed_condition")
        self.assertEqual(cause.get("detail", {}).get("prior_delay_seconds"), 120)
        self.assertEqual(detail, original, "the raw HA trace must remain immutable")

    def test_child_lock_on_same_device_is_not_the_target_entity(self):
        detail = _terrain_default_trace(entity_ref=CHILD_REGISTRY_ID)
        self.assertIsNone(unique_effect_command_rc11(_result(detail), REGISTRY))

    def test_device_id_only_is_never_accepted_from_runtime_params(self):
        detail = {
            "config": {"action": [_device_action("turn_off")]},
            "trace": {"action/0": [_runtime("switch", "turn_off", {"device_id": DEVICE_ID})]},
        }
        self.assertIsNone(unique_effect_command_rc11(_result(detail), REGISTRY))

    def test_device_action_requires_complete_exact_registry_mapping(self):
        detail = {
            "config": {"action": [_device_action("turn_off")]},
            "trace": {"action/0": [{"timestamp": "2026-09-13T21:02:27+00:00"}]},
        }
        for incomplete in (
            None,
            {"entity_id": TARGET, "device_id": DEVICE_ID},
            {"id": TARGET_REGISTRY_ID, "entity_id": TARGET},
            {**REGISTRY, "device_id": "another-device"},
            {**REGISTRY, "id": CHILD_REGISTRY_ID},
        ):
            with self.subTest(registry=incomplete):
                self.assertIsNone(unique_effect_command_rc11(_result(detail), incomplete))

    def test_result_params_have_priority_over_conflicting_config(self):
        detail = {
            "config": {"action": [_device_action("turn_off", entity_ref=CHILD_REGISTRY_ID)]},
            "trace": {
                "action/0": [
                    _runtime("switch", "turn_off", {"entity_id": TARGET})
                ]
            },
        }
        command = unique_effect_command_rc11(_result(detail), REGISTRY)
        self.assertIsNotNone(command)
        self.assertEqual(command.get("path"), "action/0")

    def test_config_is_read_only_at_the_same_executed_runtime_path(self):
        detail = {
            "config": {
                "action": [
                    _device_action("turn_off", entity_ref=CHILD_REGISTRY_ID),
                    _device_action("turn_off"),
                ]
            },
            "trace": {"action/0": [{"timestamp": "2026-09-13T21:02:27+00:00"}]},
        }
        self.assertIsNone(unique_effect_command_rc11(_result(detail), REGISTRY))

    def test_service_action_without_result_params_uses_exact_entity_target(self):
        detail = {
            "config": {
                "action": [
                    {"action": "switch.turn_off", "target": {"entity_id": TARGET}}
                ]
            },
            "trace": {"action/0": [{"timestamp": "2026-09-13T21:02:27+00:00"}]},
        }
        command = unique_effect_command_rc11(_result(detail), None)
        self.assertIsNotNone(command)
        self.assertEqual(command.get("service"), "turn_off")

    def test_completed_wait_for_trigger_without_command_params_is_preserved(self):
        detail = {
            "config": {
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [],
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
                                    _device_action("turn_off"),
                                ],
                            }
                        ]
                    }
                ]
            },
            "trace": {
                "action/0": [{"result": {"choice": 0}}],
                "action/0/choose/0": [{"result": {"result": True}}],
                "action/0/choose/0/sequence/0": [
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
                "action/0/choose/0/sequence/1": [
                    {"timestamp": "2026-09-13T22:12:27+00:00"}
                ],
            },
        }
        cause = resolve_cause_rc11(_result(detail), REGISTRY)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "wait_for_trigger")
        self.assertEqual(cause.get("command_path"), "action/0/choose/0/sequence/1")

    def test_adjacent_delay_without_command_params_is_preserved(self):
        detail = {
            "config": {
                "action": [
                    {"delay": {"hours": 1, "seconds": 1}},
                    _device_action("turn_off"),
                ]
            },
            "trace": {
                "action/0": [{"result": {"delay": 3601, "done": True}}],
                "action/1": [{"timestamp": "2026-09-13T22:00:28+00:00"}],
            },
        }
        cause = resolve_cause_rc11(_result(detail), REGISTRY)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "delay_elapsed")
        self.assertEqual(cause.get("detail", {}).get("delay_seconds"), 3601)

    async def test_activity_to_trace_to_final_record_end_to_end(self):
        main_detail = _terrain_default_trace()
        child_detail = _terrain_default_trace(entity_ref=CHILD_REGISTRY_ID)
        ha = _TerrainHA(main_detail, child_detail)
        reader = ActivityTraceReaderRC11(ha, _TraceInvestigator())
        entries = [
            {
                "entity_id": TARGET,
                "state": "off",
                "when": "2026-09-13T21:02:27+00:00",
                "context_entity_id": "automation.charge_aspirateur",
                "context_entity_id_name": "Charge aspirateur",
            }
        ]

        record = await reader._record_from_entries(
            TARGET,
            entries,
            end_time=datetime(2026, 9, 13, 21, 3, tzinfo=timezone.utc),
            hours=12,
            allow_upstream=False,
        )

        self.assertIsNotNone(record)
        self.assertEqual(record.event_kind, "turned_off")
        self.assertEqual(record.origin_type, "automation")
        self.assertEqual(record.trace_run_id, "run-main")
        self.assertEqual(record.reason_code, "ha_logbook+exact_trace")
        self.assertIn("condition", record.reason)
        answer, found = _answer_with_event_age(record)
        self.assertTrue(found)
        self.assertIn("s'est désactivé", answer)
        self.assertIn("il y a", answer)
        self.assertIn("parce qu", answer)


class _TraceInvestigator:
    async def _config_id_for_entity(self, entity_id: str):
        if entity_id == "automation.charge_aspirateur":
            return "automation", "charge_aspirateur"
        return None


class _TerrainHA:
    def __init__(self, main_detail: dict, child_detail: dict):
        self.details = {"run-main": main_detail, "run-child": child_detail}

    async def get_entity_registry(self, entity_id: str):
        return deepcopy(REGISTRY) if entity_id == TARGET else None

    async def list_traces(self, domain: str, item_id: str):
        return [
            {"run_id": "run-child", "timestamp": {"start": "2026-09-13T21:02:26+00:00"}},
            {"run_id": "run-main", "timestamp": {"start": "2026-09-13T21:00:27+00:00"}},
        ]

    async def get_trace(self, domain: str, item_id: str, run_id: str):
        return deepcopy(self.details.get(run_id))

    async def get_state(self, entity_id: str):
        if entity_id == "sensor.prise_aspirateur_power":
            return {
                "entity_id": entity_id,
                "state": "0",
                "attributes": {
                    "friendly_name": "Prise aspirateur Power",
                    "unit_of_measurement": "W",
                },
            }
        return {"entity_id": entity_id, "state": "on", "attributes": {}}


if __name__ == "__main__":
    unittest.main()

