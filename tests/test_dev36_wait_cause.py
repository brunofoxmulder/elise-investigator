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
from causal_recorder_dev33 import RelevantCausalRecorder
from targeted_memory_enricher_dev36 import TargetedMemoryEnricher

# Keep the synthetic event inside the real 12 h retention window while preserving
# the exact temporal relationships exercised by the scenario.
EVENT_TIME = (datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=10)).isoformat()


class FakeHA:
    async def get_logbook(self, entity_id, start, end):
        return [
            {
                "when": EVENT_TIME,
                "entity_id": entity_id,
                "state": "off",
                "context_id": "ctx-sdb",
                "context_event_type": "automation_triggered",
                "context_entity_id": "automation.salle_de_bain",
                "context_entity_id_name": "Salle de bain",
            }
        ]

    async def get_state(self, entity_id):
        return {
            "entity_id": entity_id,
            "state": "off",
            "attributes": {
                "friendly_name": "Mouvement salle de bain",
                "device_class": "motion",
            },
        }


class FakeTraceInvestigator:
    async def _best_trace_for_source(self, source_entity_id, event_time):
        motion_off = {
            "platform": "state",
            "entity_id": "binary_sensor.mouvement_sdb",
            "to": "off",
            "to_state": {"state": "off"},
            "idx": "0",
        }
        detail = {
            "run_id": "run-sdb",
            "trigger": {
                "platform": "state",
                "entity_id": "binary_sensor.mouvement_sdb",
                "to": "on",
                "to_state": {"state": "on"},
            },
            "config": {
                "actions": [
                    {"action": "light.turn_on", "target": {"entity_id": "light.salle_de_bain"}},
                    {
                        "wait_for_trigger": [
                            {
                                "trigger": "state",
                                "entity_id": "binary_sensor.mouvement_sdb",
                                "to": "off",
                                "for": {"minutes": 5},
                            }
                        ]
                    },
                    {"action": "light.turn_off", "target": {"entity_id": "light.salle_de_bain"}},
                ]
            },
            "trace": {
                "action/0": [
                    {
                        "result": {
                            "params": {
                                "domain": "light",
                                "service": "turn_on",
                                "target": {"entity_id": "light.salle_de_bain"},
                                "service_data": {},
                            }
                        }
                    }
                ],
                "action/1": [
                    {"result": {"wait": {"completed": True, "trigger": motion_off}}}
                ],
                "action/2": [
                    {
                        "result": {
                            "params": {
                                "domain": "light",
                                "service": "turn_off",
                                "target": {"entity_id": "light.salle_de_bain"},
                                "service_data": {},
                            }
                        }
                    }
                ],
            },
        }
        return {"summary": {"run_id": "run-sdb"}, "detail": detail}


class TestDev36WaitCause(unittest.IsolatedAsyncioTestCase):
    async def test_extinction_after_completed_no_motion_wait_uses_action_local_cause(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = RelevantCausalRecorder(Path(tmp) / "memory.sqlite3")
            stored = recorder.record(
                CausalRecord(
                    entity_id="light.salle_de_bain",
                    entity_name="Lampe salle de bain",
                    event_time=EVENT_TIME,
                    event_kind="turned_off",
                    before_value="on",
                    after_value="off",
                    origin_type="unknown",
                    confidence="confirmed",
                    trigger={"effect_context_id": "ctx-sdb"},
                )
            )
            enricher = TargetedMemoryEnricher(FakeHA(), FakeTraceInvestigator()).bind_recorder(recorder)
            await enricher.enrich([stored])
            result = recorder.get(stored.record_id)
            self.assertEqual(result.origin_type, "automation")
            self.assertEqual(result.reason, "il n'y avait plus de mouvement")
            self.assertEqual(result.trace_run_id, "run-sdb")
            self.assertEqual(result.trigger["human_cause"]["origin"], "wait_for_trigger")
            recorder.close()


if __name__ == "__main__":
    unittest.main()
