from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_resolver_v2 import has_temporal_barrier_before_effect, resolve_cause
from models import Evidence, InvestigationResult


def _result(*, after: str, trace: dict, trigger: dict) -> InvestigationResult:
    result = InvestigationResult(
        status="confirmed",
        entity_id="light.test",
        entity_name="Lampe test",
        event_type="state_change",
        event_time="2026-09-11T10:00:00+00:00",
        observed={"before": "off" if after == "on" else "on", "after": after, "attribute": None},
        cause={
            "type": "automation",
            "entity_id": "automation.test",
            "name": "Automation test",
            "system_confirmed": True,
        },
        evidence=[Evidence(kind="trace", summary="trace", strength="direct", raw=trace)],
    )
    result.chain.append({"kind": "trigger", "detail": trigger, "proven": True})
    result.chain.append({"kind": "automation", "entity_id": "automation.test", "proven": True})
    return result


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


class CausalResolverV2Tests(unittest.TestCase):
    def test_future_wait_does_not_block_presence_trigger_for_turn_on(self):
        trace = {
            "config": {
                "actions": [
                    {"variables": {"heure": "x"}},
                    {
                        "choose": [
                            {
                                "conditions": [{"condition": "template", "value_template": "true"}],
                                "sequence": [
                                    {"action": "light.turn_on", "target": {"entity_id": "light.test"}}
                                ],
                            }
                        ]
                    },
                    {
                        "wait_for_trigger": [
                            {
                                "trigger": "state",
                                "entity_id": "binary_sensor.motion",
                                "to": "off",
                                "for": "00:05:00",
                            }
                        ]
                    },
                    {"action": "light.turn_off", "target": {"entity_id": "light.test"}},
                ]
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {"platform": "state", "entity_id": "binary_sensor.motion", "from": "off", "to": "on"}}}],
                "action/1/choose/0/sequence/0": [_command("light", "turn_on", "light.test")],
                "action/2": [{"result": {"wait": {"completed": True, "trigger": {"platform": "state", "entity_id": "binary_sensor.motion", "to": "off"}}}}],
                "action/3": [_command("light", "turn_off", "light.test")],
            },
        }
        result = _result(
            after="on",
            trace=trace,
            trigger={"platform": "state", "entity_id": "binary_sensor.motion", "from": "off", "to": "on"},
        )
        self.assertFalse(
            has_temporal_barrier_before_effect(result, "action/1/choose/0/sequence/0")
        )
        cause = resolve_cause(result)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "automation_trigger")
        self.assertEqual(cause.get("detail", {}).get("entity_id"), "binary_sensor.motion")
        self.assertEqual(cause.get("detail", {}).get("to"), "on")

    def test_completed_wait_before_turn_off_is_local_cause(self):
        trace = {
            "config": {
                "actions": [
                    {"variables": {"heure": "x"}},
                    {"action": "light.turn_on", "target": {"entity_id": "light.test"}},
                    {
                        "wait_for_trigger": [
                            {
                                "trigger": "state",
                                "entity_id": "binary_sensor.motion",
                                "to": "off",
                                "for": "00:05:00",
                            }
                        ]
                    },
                    {"action": "light.turn_off", "target": {"entity_id": "light.test"}},
                ]
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {"platform": "state", "entity_id": "binary_sensor.motion", "from": "off", "to": "on"}}}],
                "action/1": [_command("light", "turn_on", "light.test")],
                "action/2": [{"result": {"wait": {"completed": True, "trigger": {"platform": "state", "entity_id": "binary_sensor.motion", "to": "off", "idx": "0"}}}}],
                "action/3": [_command("light", "turn_off", "light.test")],
            },
        }
        result = _result(
            after="off",
            trace=trace,
            trigger={"platform": "state", "entity_id": "binary_sensor.motion", "from": "off", "to": "on"},
        )
        self.assertTrue(has_temporal_barrier_before_effect(result, "action/3"))
        cause = resolve_cause(result)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "wait_for_trigger")
        self.assertEqual(cause.get("detail", {}).get("entity_id"), "binary_sensor.motion")
        self.assertEqual(cause.get("detail", {}).get("to"), "off")

    def test_preceding_delay_blocks_recycling_initial_trigger(self):
        trace = {
            "config": {
                "actions": [
                    {"delay": "00:10:00"},
                    {"action": "light.turn_on", "target": {"entity_id": "light.test"}},
                ]
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {"platform": "state", "entity_id": "binary_sensor.motion", "to": "on"}}}],
                "action/0": [{"result": {"done": True, "delay": 600}}],
                "action/1": [_command("light", "turn_on", "light.test")],
            },
        }
        result = _result(
            after="on",
            trace=trace,
            trigger={"platform": "state", "entity_id": "binary_sensor.motion", "to": "on"},
        )
        cause = resolve_cause(result)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "delay_elapsed")

    def test_time_pattern_start_trigger_is_preserved_as_structured_cause(self):
        trace = {
            "config": {
                "actions": [
                    {"action": "light.turn_on", "target": {"entity_id": "light.test"}}
                ]
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {"platform": "time_pattern", "minutes": "/10"}}}],
                "action/0": [_command("light", "turn_on", "light.test")],
            },
        }
        result = _result(
            after="on",
            trace=trace,
            trigger={"platform": "time_pattern", "minutes": "/10"},
        )
        cause = resolve_cause(result)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "automation_trigger")
        self.assertEqual(cause.get("detail", {}).get("platform"), "time_pattern")
        self.assertEqual(cause.get("detail", {}).get("minutes"), "/10")


if __name__ == "__main__":
    unittest.main()
