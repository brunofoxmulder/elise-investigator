from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from causal_recorder_dev49 import LatestPrimaryStateRecorder
from targeted_memory_enricher_dev50 import TargetedMemoryEnricher

BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=10)


def iso(seconds: float = 0) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


class FakeHA:
    def __init__(self, entry, states=None):
        self.entry = entry
        self.states = states or {}

    async def get_logbook(self, entity_id, start, end):
        return [dict(self.entry)]

    async def get_state(self, entity_id):
        return self.states.get(entity_id, {"entity_id": entity_id, "state": "unknown", "attributes": {}})


class FakeTraceInvestigator:
    def __init__(self, detail):
        self.detail = detail
        self.calls = 0

    async def _best_trace_for_source(self, source_entity_id, event_time):
        self.calls += 1
        return {"summary": {"run_id": self.detail["run_id"]}, "detail": self.detail}


def service_action(path, domain, service, entity_id, when):
    return {
        path: [
            {
                "path": path,
                "timestamp": iso(when),
                "result": {
                    "params": {
                        "domain": domain,
                        "service": service,
                        "target": {"entity_id": [entity_id]},
                        "service_data": {},
                    }
                },
            }
        ]
    }


class TestDev50PhoneAndYogurtFullCauses(unittest.IsolatedAsyncioTestCase):
    async def test_phone_charger_turn_on_recovers_hc_and_low_battery_chain(self):
        entity = "switch.chargeur_telephone_2"
        source = "automation.charge_s20_sur_prise_intelligente_1_heure_creuse"
        detail = {
            "run_id": "run-phone-on",
            "timestamp": {"start": iso(0), "finish": iso(1802)},
            "config": {
                "trigger": [
                    {"trigger": "numeric_state", "entity_id": "sensor.sm_s908b_battery_level", "below": 95}
                ],
                "condition": [
                    {"condition": "state", "entity_id": "binary_sensor.rte_tempo_heures_creuses", "state": "on"}
                ],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {"condition": "numeric_state", "entity_id": "sensor.sm_s908b_battery_level", "below": 95}
                                ],
                                "sequence": [
                                    {"delay": "00:30:00"},
                                    {"action": "switch.turn_on", "target": {"entity_id": [entity]}},
                                ],
                            },
                            {
                                "conditions": [
                                    {"condition": "numeric_state", "entity_id": "sensor.sm_s908b_battery_level", "above": 99}
                                ],
                                "sequence": [
                                    {"action": "switch.turn_off", "target": {"entity_id": [entity]}},
                                ],
                            },
                        ]
                    }
                ],
            },
            "trigger": {
                "platform": "numeric_state",
                "entity_id": "sensor.sm_s908b_battery_level",
                "below": 95,
                "from_state": {"state": "96", "attributes": {"friendly_name": "S20 batterie", "unit_of_measurement": "%"}},
                "to_state": {"state": "94", "attributes": {"friendly_name": "S20 batterie", "unit_of_measurement": "%"}},
            },
            "trace": {
                "condition/0": [{"result": {"result": True, "state": "on"}}],
                "action/0": [{"timestamp": iso(1), "result": {"choice": 0}}],
                "action/0/choose/0/conditions/0": [{"result": {"result": True, "state": "94"}}],
                "action/0/choose/0/sequence/0": [{"timestamp": iso(1), "result": {"delay": 1800.0, "done": True}}],
                **service_action("action/0/choose/0/sequence/1", "switch", "turn_on", entity, 1801),
            },
        }
        entry = {
            "when": iso(1801), "entity_id": entity, "state": "on", "context_id": "ctx-phone-on",
            "context_event_type": "automation_triggered", "context_entity_id": source,
            "context_entity_id_name": "charge S20 sur prise intelligente 1 heure creuse",
        }
        states = {
            "sensor.sm_s908b_battery_level": {"entity_id": "sensor.sm_s908b_battery_level", "state": "94", "attributes": {"friendly_name": "S20 batterie", "unit_of_measurement": "%"}},
            "binary_sensor.rte_tempo_heures_creuses": {"entity_id": "binary_sensor.rte_tempo_heures_creuses", "state": "on", "attributes": {"friendly_name": "Heures creuses"}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            recorder = LatestPrimaryStateRecorder(Path(tmp) / "memory.sqlite3")
            stored = recorder.record(CausalRecord(entity_id=entity, entity_name="Chargeur téléphone 2", event_time=iso(1801), event_kind="turned_on", before_value="off", after_value="on", origin_type="unknown", confidence="confirmed", trigger={"effect_context_id": "ctx-phone-on", "effect_parent_id": None}))
            traces = FakeTraceInvestigator(detail)
            enricher = TargetedMemoryEnricher(FakeHA(entry, states), traces).bind_recorder(recorder)
            changed = await enricher.enrich([stored])
            result = recorder.get(stored.record_id)
            self.assertTrue(changed)
            self.assertEqual(result.origin_type, "automation")
            self.assertEqual(result.source_entity_id, source)
            self.assertIsNotNone(result.reason)
            self.assertTrue("95" in result.reason or "batter" in result.reason.lower())
            recorder.close()

    async def test_phone_charger_turn_off_recovers_full_battery_cause(self):
        entity = "switch.chargeur_telephone_2"
        source = "automation.charge_s20_sur_prise_intelligente_1_heure_creuse"
        detail = {
            "run_id": "run-phone-off",
            "timestamp": {"start": iso(0), "finish": iso(2)},
            "config": {
                "trigger": [{"trigger": "numeric_state", "entity_id": "sensor.sm_s908b_battery_level", "above": 99}],
                "condition": [{"condition": "state", "entity_id": "binary_sensor.rte_tempo_heures_creuses", "state": "on"}],
                "action": [{"choose": [
                    {"conditions": [{"condition": "numeric_state", "entity_id": "sensor.sm_s908b_battery_level", "below": 95}], "sequence": [{"delay": "00:30:00"}, {"action": "switch.turn_on", "target": {"entity_id": [entity]}}]},
                    {"conditions": [{"condition": "numeric_state", "entity_id": "sensor.sm_s908b_battery_level", "above": 99}], "sequence": [{"action": "switch.turn_off", "target": {"entity_id": [entity]}}]},
                ]}],
            },
            "trigger": {
                "platform": "numeric_state", "entity_id": "sensor.sm_s908b_battery_level", "above": 99,
                "from_state": {"state": "99", "attributes": {"friendly_name": "S20 batterie", "unit_of_measurement": "%"}},
                "to_state": {"state": "100", "attributes": {"friendly_name": "S20 batterie", "unit_of_measurement": "%"}},
            },
            "trace": {
                "condition/0": [{"result": {"result": True, "state": "on"}}],
                "action/0": [{"timestamp": iso(0.5), "result": {"choice": 1}}],
                "action/0/choose/1/conditions/0": [{"result": {"result": True, "state": "100"}}],
                **service_action("action/0/choose/1/sequence/0", "switch", "turn_off", entity, 1),
            },
        }
        entry = {"when": iso(1), "entity_id": entity, "state": "off", "context_id": "ctx-phone-off", "context_event_type": "automation_triggered", "context_entity_id": source, "context_entity_id_name": "charge S20 sur prise intelligente 1 heure creuse"}
        with tempfile.TemporaryDirectory() as tmp:
            recorder = LatestPrimaryStateRecorder(Path(tmp) / "memory.sqlite3")
            stored = recorder.record(CausalRecord(entity_id=entity, entity_name="Chargeur téléphone 2", event_time=iso(1), event_kind="turned_off", before_value="on", after_value="off", origin_type="unknown", confidence="confirmed", trigger={"effect_context_id": "ctx-phone-off", "effect_parent_id": None}))
            enricher = TargetedMemoryEnricher(FakeHA(entry), FakeTraceInvestigator(detail)).bind_recorder(recorder)
            changed = await enricher.enrich([stored])
            result = recorder.get(stored.record_id)
            self.assertTrue(changed)
            self.assertEqual(result.source_entity_id, source)
            self.assertIsNotNone(result.reason)
            self.assertTrue("99" in result.reason or "batter" in result.reason.lower())
            recorder.close()

    async def test_yogurt_turn_off_recovers_12_hour_cycle_cause(self):
        entity = "switch.yaourtiere"
        source = "automation.aaaayaourt"
        detail = {
            "run_id": "run-yogurt-12h",
            "timestamp": {"start": iso(-43200), "finish": iso(2)},
            "config": {
                "trigger": [{"trigger": "state", "entity_id": entity, "from": "off", "to": "on"}],
                "condition": [],
                "action": [{"delay": "12:00:00"}, {"action": "switch.turn_off", "target": {"entity_id": entity}}],
            },
            "trigger": {
                "platform": "state", "entity_id": entity, "from": "off", "to": "on",
                "from_state": {"state": "off", "attributes": {"friendly_name": "Yaourtière"}},
                "to_state": {"state": "on", "attributes": {"friendly_name": "Yaourtière"}},
            },
            "trace": {
                "action/0": [{"timestamp": iso(-43200), "result": {"delay": 43200.0, "done": True}}],
                **service_action("action/1", "switch", "turn_off", entity, 1),
            },
        }
        entry = {"when": iso(1), "entity_id": entity, "state": "off", "context_id": "ctx-yogurt", "context_event_type": "automation_triggered", "context_entity_id": source, "context_entity_id_name": "Aaaayaourt"}
        with tempfile.TemporaryDirectory() as tmp:
            recorder = LatestPrimaryStateRecorder(Path(tmp) / "memory.sqlite3")
            stored = recorder.record(CausalRecord(entity_id=entity, entity_name="Yaourtière", event_time=iso(1), event_kind="turned_off", before_value="on", after_value="off", origin_type="unknown", confidence="confirmed", trigger={"effect_context_id": "ctx-yogurt", "effect_parent_id": None}))
            enricher = TargetedMemoryEnricher(FakeHA(entry), FakeTraceInvestigator(detail)).bind_recorder(recorder)
            changed = await enricher.enrich([stored])
            result = recorder.get(stored.record_id)
            self.assertTrue(changed)
            self.assertEqual(result.source_entity_id, source)
            self.assertIsNotNone(result.reason)
            self.assertTrue("yaour" in result.reason.lower() or "on" in result.reason.lower())
            recorder.close()


if __name__ == "__main__":
    unittest.main()
