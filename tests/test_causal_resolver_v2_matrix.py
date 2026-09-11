from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_dev60 import select_activity_entry
from causal_resolver_v2 import resolve_cause, unique_effect_command
from models import Evidence, InvestigationResult


def _command(domain: str, service: str, target: str, data: dict | None = None) -> dict:
    params = {
        "domain": domain,
        "service": service,
        "target": {"entity_id": target},
    }
    if data is not None:
        params["service_data"] = data
    return {"result": {"params": params}}


def _result(
    *,
    entity_id: str,
    after,
    trace: dict,
    trigger: dict | None = None,
    attribute: str | None = None,
    cause_type: str = "automation",
) -> InvestigationResult:
    result = InvestigationResult(
        status="confirmed",
        entity_id=entity_id,
        entity_name=entity_id,
        event_type="state_change",
        event_time="2026-09-11T10:00:00+00:00",
        observed={"before": None, "after": after, "attribute": attribute},
        cause={
            "type": cause_type,
            "entity_id": "automation.test" if cause_type == "automation" else None,
            "name": "Automation test" if cause_type == "automation" else None,
            "system_confirmed": True,
        },
        evidence=[Evidence(kind="trace", summary="trace", strength="direct", raw=trace)],
    )
    if trigger:
        result.chain.append({"kind": "trigger", "detail": trigger, "proven": True})
    if cause_type == "automation":
        result.chain.append({"kind": "automation", "entity_id": "automation.test", "proven": True})
    return result


class CausalResolverV2TerrainMatrix(unittest.TestCase):
    def test_cover_set_position_matches_primary_open_effect(self):
        target = "cover.volet_salon_2"
        trace = {
            "config": {
                "actions": [
                    {"action": "cover.set_cover_position", "target": {"entity_id": target}, "data": {"position": 80}}
                ]
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {"platform": "time_pattern", "minutes": "/10"}}}],
                "action/0": [_command("cover", "set_cover_position", target, {"position": 80})],
            },
        }
        result = _result(
            entity_id=target,
            after="open",
            trace=trace,
            trigger={"platform": "time_pattern", "minutes": "/10"},
        )
        command = unique_effect_command(result)
        self.assertIsNotNone(command)
        self.assertEqual(command.get("service"), "set_cover_position")
        cause = resolve_cause(result)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "automation_trigger")
        self.assertEqual(cause.get("detail", {}).get("platform"), "time_pattern")

    def test_cover_set_position_matches_exact_position_attribute(self):
        target = "cover.volet_salon_2"
        trace = {
            "config": {
                "actions": [
                    {"action": "cover.set_cover_position", "target": {"entity_id": target}, "data": {"position": 30}}
                ]
            },
            "trace": {
                "action/0": [_command("cover", "set_cover_position", target, {"position": 30})],
            },
        }
        result = _result(
            entity_id=target,
            after=30,
            attribute="current_position",
            trace=trace,
            trigger={"platform": "numeric_state", "entity_id": "sensor.lux", "above": 25000},
        )
        self.assertIsNotNone(unique_effect_command(result))

    def test_heures_creuses_and_low_battery_remain_joint_causes_across_delay(self):
        target = "switch.prise_intelligente_l4"
        trace = {
            "config": {
                "triggers": [
                    {"trigger": "state", "entity_id": "binary_sensor.rte_tempo_heures_creuses", "to": "on"},
                    {"trigger": "numeric_state", "entity_id": "sensor.sm_s918b_battery_level", "below": 95},
                    {"trigger": "numeric_state", "entity_id": "sensor.sm_s918b_battery_level", "above": 99},
                ],
                "conditions": [
                    {"condition": "state", "entity_id": "binary_sensor.rte_tempo_heures_creuses", "state": "on"}
                ],
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
                            }
                        ]
                    }
                ],
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {"platform": "state", "entity_id": "binary_sensor.rte_tempo_heures_creuses", "to": "on"}}}],
                "condition/0": [{"result": {"result": True, "state": "on"}}],
                "action/0/choose/0/conditions/0": [{"result": {"result": True, "state": "72"}}],
                "action/0/choose/0/sequence/0": [{"result": {"done": True, "delay": 1800}}],
                "action/0/choose/0/sequence/1": [_command("switch", "turn_on", target)],
            },
        }
        result = _result(
            entity_id=target,
            after="on",
            trace=trace,
            trigger={"platform": "state", "entity_id": "binary_sensor.rte_tempo_heures_creuses", "to": "on"},
        )
        cause = resolve_cause(result)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "causal_sequence")
        factors = cause.get("detail", {}).get("factors", [])
        self.assertEqual(len(factors), 2)
        ids = {factor.get("proof_entity_id") for factor in factors}
        self.assertEqual(
            ids,
            {"binary_sensor.rte_tempo_heures_creuses", "sensor.sm_s918b_battery_level"},
        )
        self.assertEqual(cause.get("detail", {}).get("release", {}).get("origin"), "delay_elapsed")

    def test_pure_state_guard_is_not_promoted(self):
        target = "light.test"
        trace = {
            "config": {
                "conditions": [
                    {"condition": "state", "entity_id": "input_boolean.mode_cinema", "state": "off"}
                ],
                "actions": [{"action": "light.turn_on", "target": {"entity_id": target}}],
            },
            "trace": {
                "condition/0": [{"result": {"result": True, "state": "off"}}],
                "action/0": [_command("light", "turn_on", target)],
            },
        }
        trigger = {"platform": "state", "entity_id": "binary_sensor.motion", "to": "on"}
        result = _result(entity_id=target, after="on", trace=trace, trigger=trigger)
        cause = resolve_cause(result)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "automation_trigger")
        self.assertEqual(cause.get("detail", {}).get("entity_id"), "binary_sensor.motion")

    def test_user_origin_is_never_reinterpreted_by_automation_resolver(self):
        target = "light.test"
        result = _result(
            entity_id=target,
            after="off",
            trace={"config": {}, "trace": {}},
            cause_type="user",
        )
        self.assertIsNone(resolve_cause(result))

    def test_unavailable_unknown_do_not_replace_latest_functional_activity_fact(self):
        entity = "switch.tineco"
        entries = [
            {"entity_id": entity, "state": "on", "when": "2026-09-11T10:00:00+00:00"},
            {"entity_id": entity, "state": "unavailable", "when": "2026-09-11T10:05:00+00:00"},
            {"entity_id": entity, "state": "unknown", "when": "2026-09-11T10:05:01+00:00"},
        ]
        selected = select_activity_entry(entries, entity)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.get("state"), "on")
        self.assertEqual(selected.get("when"), "2026-09-11T10:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
