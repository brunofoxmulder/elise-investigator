from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_dev70 import ActivityTraceReader as Dev70ActivityTraceReader
from activity_reader_dev71 import ActivityTraceReader
from causal_recorder import CausalRecord
from models import Evidence, InvestigationResult
from targeted_memory_enricher_dev71 import TargetedMemoryEnricher
from trace_action_local_dev71 import select_adjacent_temporal_cause


class _HA:
    async def get_state(self, entity_id):
        names = {
            "binary_sensor.heures_creuses": ("Heures creuses", None),
            "sensor.battery": ("Batterie", "%"),
            "input_boolean.guard": ("Garde", None),
        }
        name, unit = names.get(entity_id, (entity_id, None))
        attrs = {"friendly_name": name}
        if unit:
            attrs["unit_of_measurement"] = unit
        return {"entity_id": entity_id, "state": "on", "attributes": attrs}


class _TraceInvestigator:
    pass


def _record(entity_id: str, after: str = "on") -> CausalRecord:
    return CausalRecord(
        entity_id=entity_id,
        event_time="2026-09-10T20:30:26+00:00",
        event_kind="turned_on" if after == "on" else "turned_off",
        after_value=after,
        origin_type="automation",
        source_entity_id="automation.test",
        source_name="Test",
        confidence="confirmed",
    )


def _result(entity_id: str, after: str, detail: dict) -> InvestigationResult:
    return InvestigationResult(
        status="confirmed",
        entity_id=entity_id,
        entity_name=entity_id,
        event_type="state_changed",
        event_time="2026-09-10T20:30:26+00:00",
        observed={"before": None, "after": after, "attribute": None},
        cause={
            "type": "automation",
            "entity_id": "automation.test",
            "name": "Test",
            "system_confirmed": True,
        },
        evidence=[Evidence(kind="trace", summary="trace", source="automation.test", strength="direct", raw=detail)],
    )


class Dev71CausalSemanticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_activity_triggered_by_text_is_never_final_reason(self):
        record = _record("switch.aspirateur", "off")
        record.reason = "triggered by state of binary_sensor.heures_creuses"
        record.reason_code = "ha_2026_9_activity_source_hint"

        reader = ActivityTraceReader(_HA())
        with patch.object(
            Dev70ActivityTraceReader,
            "_record_from_entries",
            new=AsyncMock(return_value=record),
        ):
            result = await reader._record_from_entries(
                "switch.aspirateur",
                [],
                end_time=None,
                hours=24,
                allow_upstream=False,
            )

        self.assertIs(result, record)
        self.assertIsNone(result.reason)
        self.assertIsNone(result.reason_code)

    async def test_guard_condition_is_not_promoted_to_primary_cause(self):
        detail = {
            "config": {
                "actions": [{
                    "choose": [{
                        "conditions": [{
                            "condition": "state",
                            "entity_id": "input_boolean.guard",
                            "state": "on",
                        }],
                        "sequence": [{
                            "action": "switch.turn_on",
                            "target": {"entity_id": "switch.target"},
                        }],
                    }]
                }]
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {"platform": "time_pattern", "minutes": "/5"}}}],
                "action/0": [{"result": {"choice": 0}}],
                "action/0/choose/0": [{"result": {"result": True}}],
                "action/0/choose/0/conditions/0": [{"result": {"result": True, "state": "on"}}],
                "action/0/choose/0/sequence/0": [{"result": {"params": {
                    "domain": "switch",
                    "service": "turn_on",
                    "target": {"entity_id": ["switch.target"]},
                }}}],
            },
        }
        helper = TargetedMemoryEnricher(_HA(), _TraceInvestigator())
        reason, _, cause = await helper._reason_from_detail(
            _record("switch.target"),
            "automation.test",
            "Test",
            "automation",
            detail,
            "run-guard",
        )

        # time_pattern has no supported final human sentence: fail closed on wording,
        # while retaining only the proven automation trigger in the compact proof.
        self.assertIsNone(reason)
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "automation_trigger")
        self.assertNotIn("input_boolean.guard", str(cause))

    async def test_proven_state_trigger_keeps_joint_required_condition(self):
        detail = {
            "config": {
                "conditions": [{"condition": "numeric_state", "entity_id": "sensor.battery", "below": 40}],
                "actions": [{"action": "switch.turn_on", "target": {"entity_id": "switch.telephone"}}],
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {
                    "platform": "state",
                    "entity_id": "binary_sensor.heures_creuses",
                    "from_state": {"state": "off"},
                    "to_state": {"state": "on"},
                }}}],
                "condition/0": [{"result": {"result": True, "state": "32"}}],
                "action/0": [{"result": {"params": {
                    "domain": "switch",
                    "service": "turn_on",
                    "target": {"entity_id": ["switch.telephone"]},
                }}}],
            },
        }
        helper = TargetedMemoryEnricher(_HA(), _TraceInvestigator())
        reason, _, cause = await helper._reason_from_detail(
            _record("switch.telephone"),
            "automation.test",
            "Test",
            "automation",
            detail,
            "run-joint",
        )

        # The compact proof intentionally omits nested condition arrays. The conjunction
        # is verified by its semantic origin plus the human sentence built from both
        # proven atoms, matching the existing dev.68 presentation contract.
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "trigger_plus_conditions")
        self.assertIsNotNone(reason)
        self.assertIn("Heures creuses", reason)
        self.assertIn("Batterie", reason)
        self.assertIn(" et ", reason)

    def test_nested_delay_adjacent_to_target_is_action_local_cause(self):
        detail = {
            "config": {
                "actions": [{
                    "choose": [{
                        "conditions": [],
                        "sequence": [
                            {"delay": "00:10:00"},
                            {"action": "switch.turn_off", "target": {"entity_id": "switch.aspirateur"}},
                        ],
                    }]
                }]
            },
            "trace": {
                "action/0": [{"result": {"choice": 0}}],
                "action/0/choose/0": [{"result": {"result": True}}],
                "action/0/choose/0/sequence/0": [{"result": {"result": True}}],
                "action/0/choose/0/sequence/1": [{"result": {"params": {
                    "domain": "switch",
                    "service": "turn_off",
                    "target": {"entity_id": ["switch.aspirateur"]},
                }}}],
            },
        }
        cause = select_adjacent_temporal_cause(_result("switch.aspirateur", "off", detail))
        self.assertIsNotNone(cause)
        self.assertEqual(cause.get("origin"), "delay_elapsed")
        self.assertEqual(cause.get("path"), "action/0/choose/0/sequence/0")

    async def test_executed_wait_template_blocks_recycled_initial_trigger(self):
        detail = {
            "config": {
                "actions": [
                    {"wait_template": "{{ is_state('binary_sensor.ready', 'on') }}", "timeout": "01:00:00"},
                    {"action": "switch.turn_on", "target": {"entity_id": "switch.target"}},
                ]
            },
            "trace": {
                "trigger/0": [{"changed_variables": {"trigger": {
                    "platform": "state",
                    "entity_id": "binary_sensor.heures_creuses",
                    "from_state": {"state": "off"},
                    "to_state": {"state": "on"},
                }}}],
                "action/0": [{"result": {"result": True}}],
                "action/1": [{"result": {"params": {
                    "domain": "switch",
                    "service": "turn_on",
                    "target": {"entity_id": ["switch.target"]},
                }}}],
            },
        }
        helper = TargetedMemoryEnricher(_HA(), _TraceInvestigator())
        reason, _, cause = await helper._reason_from_detail(
            _record("switch.target"),
            "automation.test",
            "Test",
            "automation",
            detail,
            "run-wait-template",
        )

        self.assertIsNone(reason)
        self.assertIsNone(cause)

    def test_dev54_fallback_entrypoint_remains_present(self):
        fallback = (APP / "main_dev54.py").read_text()
        self.assertIn('VERSION = "0.2.0-dev.54"', fallback)


if __name__ == "__main__":
    unittest.main()
