"""Anonymized RC11 terrain shapes: immediate device ON before a later wait/delay.

The HA MCP summaries flatten State objects; fixtures restore their documented
state dictionaries. Entity/registry IDs are synthetic. No HA connection is used.
"""
from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from causal_resolver_rc11 import resolve_cause_rc11
from main_v2_rc11 import _answer_with_event_age
from targeted_memory_enricher_v2 import TargetedMemoryEnricherV2

from causal_resolver_rc12 import resolve_cause_rc12 as resolve_candidate
from activity_reader_rc12 import ActivityTraceReaderRC12 as CandidateReader

SOURCE = "automation.recharge_station"
TRIGGER = "binary_sensor.tariff_window"
STAMP = "2026-09-15T20:00:04+00:00"
TARGETS = ("switch.recharge_station", "switch.brush_station")


def registry(target):
    return {"id": target.replace(".", "_") + "_registry", "entity_id": target,
            "device_id": target.replace(".", "_") + "_device"}


def device_action(target, action_type):
    entry = registry(target)
    return {"domain": "switch", "type": action_type,
            "entity_id": entry["id"], "device_id": entry["device_id"]}


def runtime_command(target, service="turn_on"):
    return {"timestamp": STAMP, "result": {"params": {
        "domain": "switch", "service": service, "target": {"entity_id": target}}}}


def trace(target=TARGETS[0], *, completed=False):
    """ON has no runtime params; the following temporal action cannot explain it."""
    delay = 3601 if completed else 120
    runtime_trigger = {"platform": "device", "entity_id": TRIGGER,
                       "from_state": {"state": "off"}, "to_state": {"state": "on"}}
    detail = {
        "config": {"trigger": [{"platform": "device", "type": "turned_on",
                                  "entity_id": "trigger-registry"}],
                   "action": [device_action(target, "turn_on"), {"delay": delay},
                              device_action(target, "turn_off")]},
        "trace": {
            "trigger/0": [{"timestamp": STAMP,
                           "changed_variables": {"trigger": runtime_trigger}}],
            "action/0": [{"timestamp": STAMP}],
            "action/1": [{"timestamp": STAMP, "result": {"delay": delay, "done": True}}],
        },
    }
    if completed:
        detail["trace"]["action/2"] = [{"timestamp": "2026-09-15T21:00:05+00:00"}]
    else:
        detail["config"]["action"][2] = {"choose": [{
            "conditions": [{"condition": "numeric_state", "entity_id": "sensor.station_power", "above": 1}],
            "sequence": [{"wait_for_trigger": [{"trigger": "numeric_state", "entity_id": "sensor.station_power", "below": 1}]},
                         device_action(target, "turn_off")]}]}
        detail["trace"].update({
            "action/2": [{"result": {"choice": 0}}],
            "action/2/choose/0/conditions/0": [{"result": {"result": True, "state": 11}}],
            "action/2/choose/0/sequence/0": [{"result": {"result": False, "state": 11, "wanted_state_below": 1}}],
        })
    return detail


def result(detail, target=TARGETS[0], after="on"):
    record = CausalRecord(entity_id=target, event_time=STAMP,
                          event_kind="turned_on" if after == "on" else "turned_off",
                          before_value="off" if after == "on" else "on", after_value=after)
    return TargetedMemoryEnricherV2._result(record, SOURCE, "Recharge station", "automation", detail)


class ReadOnlyHA:
    def __init__(self, detail, target):
        self.detail, self.target = detail, target

    async def get_entity_registry(self, entity_id):
        return registry(entity_id) if entity_id == self.target else None

    async def list_traces(self, domain, item_id):
        return [{"run_id": "exact-run", "timestamp": {"start": STAMP}}]

    async def get_trace(self, domain, item_id, run_id):
        return deepcopy(self.detail)

    async def get_state(self, entity_id):
        return {"entity_id": entity_id, "state": "on",
                "attributes": {"friendly_name": "Tariff window" if entity_id == TRIGGER else entity_id}}


class TraceInvestigator:
    async def _config_id_for_entity(self, entity_id):
        return ("automation", "recharge_station") if entity_id == SOURCE else None


class RC12StartTriggerTests(unittest.IsolatedAsyncioTestCase):
    def test_rc11_reproduces_both_missing_on_causes(self):
        for target, completed in zip(TARGETS, (False, True)):
            with self.subTest(target=target):
                value = result(trace(target, completed=completed), target)
                self.assertEqual(value.chain, [])
                self.assertIsNone(resolve_cause_rc11(value, registry(target)))

    def assert_start_trigger(self, value, target=TARGETS[0]):
        cause = resolve_candidate(value, registry(target))
        self.assertIsNotNone(cause)
        self.assertEqual(cause["origin"], "automation_trigger")
        self.assertEqual(cause["detail"]["entity_id"], TRIGGER)
        self.assertEqual(cause["detail"]["to_state"]["state"], "on")

    def test_immediate_on_before_running_wait_uses_start_trigger(self):
        self.assert_start_trigger(result(trace()))

    def test_immediate_on_before_completed_delay_uses_start_trigger(self):
        self.assert_start_trigger(result(trace(TARGETS[1], completed=True), TARGETS[1]), TARGETS[1])

    def test_input_trace_and_chain_remain_unchanged(self):
        value = result(trace())
        before = deepcopy(value)
        self.assert_start_trigger(value)
        self.assertEqual(value, before)

    def test_config_trigger_without_runtime_trigger_is_not_proof(self):
        detail = trace()
        del detail["trace"]["trigger/0"]
        self.assertIsNone(resolve_candidate(result(detail), registry(TARGETS[0])))

    def test_config_action_without_executed_path_is_not_proof(self):
        detail = trace()
        del detail["trace"]["action/0"]
        self.assertIsNone(resolve_candidate(result(detail), registry(TARGETS[0])))

    def test_child_lock_on_same_device_is_rejected(self):
        detail = trace()
        detail["config"]["action"][0]["entity_id"] = "child-lock-registry"
        self.assertIsNone(resolve_candidate(result(detail), registry(TARGETS[0])))

    def test_missing_or_incorrect_registry_is_rejected(self):
        for entry in (None, {"entity_id": TARGETS[0]},
                      {**registry(TARGETS[0]), "device_id": "other-device"}):
            with self.subTest(entry=entry):
                self.assertIsNone(resolve_candidate(result(trace()), entry))

    def test_runtime_other_target_is_not_overridden_by_config(self):
        detail = trace()
        detail["trace"]["action/0"] = [runtime_command("switch.other")]
        self.assertIsNone(resolve_candidate(result(detail), registry(TARGETS[0])))

    def test_runtime_device_only_is_not_overridden_by_config(self):
        detail = trace()
        node = runtime_command(TARGETS[0])
        node["result"]["params"]["target"] = {"device_id": registry(TARGETS[0])["device_id"]}
        detail["trace"]["action/0"] = [node]
        self.assertIsNone(resolve_candidate(result(detail), registry(TARGETS[0])))

    def test_existing_service_trigger_cause_is_unchanged(self):
        detail = trace()
        detail["trace"]["action/0"] = [runtime_command(TARGETS[0])]
        detail["config"]["action"][0]["entity_id"] = "wrong-config-reference"
        value = result(detail)
        expected = resolve_cause_rc11(value, registry(TARGETS[0]))
        self.assertIsNotNone(expected)
        self.assertEqual(resolve_candidate(value, registry(TARGETS[0])), expected)

    def test_delayed_off_still_uses_delay_not_start_trigger(self):
        value = result(trace(completed=True), after="off")
        expected = resolve_cause_rc11(value, registry(TARGETS[0]))
        self.assertEqual(expected["origin"], "delay_elapsed")
        self.assertEqual(resolve_candidate(value, registry(TARGETS[0])), expected)

    def test_unresolved_earlier_barrier_blocks_start_trigger(self):
        detail = trace()
        detail["config"]["action"] = [{"wait_template": "{{ ready }}"}, {"variables": {"x": 1}}, device_action(TARGETS[0], "turn_on")]
        detail["trace"] = {"trigger/0": detail["trace"]["trigger/0"],
                           "action/0": [{"timestamp": STAMP}],
                           "action/1": [{"timestamp": STAMP}],
                           "action/2": [{"timestamp": STAMP}]}
        self.assertIsNone(resolve_candidate(result(detail), registry(TARGETS[0])))

    def test_ambiguous_repeated_on_commands_are_rejected(self):
        detail = trace()
        detail["config"]["action"].append(device_action(TARGETS[0], "turn_on"))
        detail["trace"]["action/3"] = [{"timestamp": STAMP}]
        self.assertIsNone(resolve_candidate(result(detail), registry(TARGETS[0])))

    async def test_activity_to_final_record_for_both_on_paths(self):
        for target, completed in zip(TARGETS, (False, True)):
            with self.subTest(target=target):
                detail = trace(target, completed=completed)
                reader = CandidateReader(ReadOnlyHA(detail, target), TraceInvestigator())
                record = await reader._record_from_entries(target, [{
                    "entity_id": target, "state": "on", "when": STAMP,
                    "context_entity_id": SOURCE, "context_entity_id_name": "Recharge station",
                    "context_message": "triggered by state of binary_sensor.tariff_window",
                }], end_time=datetime(2026, 9, 15, 20, 1, tzinfo=timezone.utc), hours=12, allow_upstream=False)
                self.assertEqual(record.trace_run_id, "exact-run")
                self.assertEqual(record.reason_code, "ha_logbook+exact_trace")
                self.assertIn("Tariff window", record.reason)
                answer, found = _answer_with_event_age(record)
                self.assertTrue(found)
                self.assertIn("il y a", answer)
                self.assertNotIn("triggered", answer)
                self.assertNotIn("délai", answer)


if __name__ == "__main__":
    unittest.main()
