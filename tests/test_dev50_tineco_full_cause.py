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
    async def get_logbook(self, entity_id, start, end):
        return [
            {
                "when": iso(2),
                "entity_id": "switch.0xa4c1387da600c253",
                "state": "off",
                "context_id": "ctx-tineco-100",
                "context_event_type": "automation_triggered",
                "context_entity_id": "automation.couper_prise_tineco_quand_charge_terminee",
                "context_entity_id_name": "Couper prise Tineco quand charge terminée",
                "context_source": "numeric state of sensor.tineco_battery",
            }
        ]

    async def get_state(self, entity_id):
        if entity_id == "sensor.tineco_battery":
            return {
                "entity_id": entity_id,
                "state": "100",
                "attributes": {
                    "friendly_name": "Tineco Device Tineco Battery",
                    "unit_of_measurement": "%",
                },
            }
        return {"entity_id": entity_id, "state": "off", "attributes": {}}


class FakeTraceInvestigator:
    def __init__(self):
        self.calls = 0

    async def _best_trace_for_source(self, source_entity_id, event_time):
        self.calls += 1
        return {
            "summary": {"run_id": "run-tineco-100"},
            "detail": {
                "run_id": "run-tineco-100",
                "timestamp": {"start": iso(0), "finish": iso(3)},
                "config": {
                    "trigger": [
                        {
                            "trigger": "numeric_state",
                            "entity_id": ["sensor.tineco_battery"],
                            "above": 99.9,
                        }
                    ],
                    "condition": [],
                    "action": [
                        {
                            "action": "switch.turn_off",
                            "target": {"entity_id": "switch.0xa4c1387da600c253"},
                            "data": {},
                        },
                        {
                            "action": "notify.mobile_app_sm_s918b",
                            "data": {
                                "title": "Tineco S7 Pro",
                                "message": "Le S7 Pro est chargé",
                            },
                        },
                    ],
                },
                "trigger": {
                    "platform": "numeric_state",
                    "entity_id": "sensor.tineco_battery",
                    "above": 99.9,
                    "from_state": {
                        "state": "99",
                        "attributes": {
                            "friendly_name": "Tineco Device Tineco Battery",
                            "unit_of_measurement": "%",
                        },
                    },
                    "to_state": {
                        "state": "100",
                        "attributes": {
                            "friendly_name": "Tineco Device Tineco Battery",
                            "unit_of_measurement": "%",
                        },
                    },
                },
                "trace": {
                    "action/0": [
                        {
                            "path": "action/0",
                            "timestamp": iso(1),
                            "result": {
                                "params": {
                                    "domain": "switch",
                                    "service": "turn_off",
                                    "target": {"entity_id": ["switch.0xa4c1387da600c253"]},
                                    "service_data": {},
                                }
                            },
                        }
                    ],
                    "action/1": [
                        {
                            "path": "action/1",
                            "timestamp": iso(2.5),
                            "result": {"done": True},
                        }
                    ],
                },
            },
        }


class TestDev50TinecoFullCause(unittest.IsolatedAsyncioTestCase):
    async def test_tineco_off_replays_real_archived_automation_and_recovers_battery_cause(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = LatestPrimaryStateRecorder(Path(tmp) / "memory.sqlite3")
            stored = recorder.record(
                CausalRecord(
                    entity_id="switch.0xa4c1387da600c253",
                    entity_name="Tineco",
                    event_time=iso(2),
                    event_kind="turned_off",
                    before_value="on",
                    after_value="off",
                    origin_type="unknown",
                    confidence="confirmed",
                    trigger={
                        "effect_context_id": "ctx-tineco-100",
                        "effect_parent_id": None,
                    },
                )
            )
            traces = FakeTraceInvestigator()
            enricher = TargetedMemoryEnricher(FakeHA(), traces).bind_recorder(recorder)

            changed = await enricher.enrich([stored])
            result = recorder.get(stored.record_id)

            self.assertTrue(changed)
            self.assertEqual(traces.calls, 1)
            self.assertEqual(result.origin_type, "automation")
            self.assertEqual(
                result.source_entity_id,
                "automation.couper_prise_tineco_quand_charge_terminee",
            )
            self.assertEqual(result.trace_run_id, "run-tineco-100")
            self.assertIsNotNone(result.reason)
            self.assertIn("99", result.reason)
            self.assertIn("dépass", result.reason.lower())
            self.assertIn("tineco", result.reason.lower())
            recorder.close()


if __name__ == "__main__":
    unittest.main()
