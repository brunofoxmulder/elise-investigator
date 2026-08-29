from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import memory_worker_dev34 as memory_base
from causal_events import ObservedChange
from causal_recorder import CausalRecord, CausalRecorder
from main_dev37 import configure_dev37
from memory_worker_dev34 import ConsciousMemoryWorker
from targeted_memory_enricher_dev37 import TargetedMemoryEnricher

# Keep dev.37 regression scenarios representative of the live 12 h memory window.
BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=10)


def iso(seconds: float = 0) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


class FakeHA:
    def __init__(self, entries=None, states=None):
        self.entries = list(entries or [])
        self.states = dict(states or {})
        self.logbook_calls = 0
        self.state_calls = 0

    async def get_logbook(self, entity_id, start, end):
        self.logbook_calls += 1
        return list(self.entries)

    async def get_state(self, entity_id):
        self.state_calls += 1
        return self.states.get(
            entity_id,
            {"entity_id": entity_id, "state": "off", "attributes": {}},
        )


class ExplodingHA(FakeHA):
    async def get_logbook(self, entity_id, start, end):
        raise AssertionError("cover terminal continuity must not re-query Logbook")


class FakeTraceInvestigator:
    def __init__(self, detail):
        self.detail = detail
        self.calls = 0

    async def _best_trace_for_source(self, source_entity_id, event_time):
        self.calls += 1
        return {
            "summary": {"run_id": self.detail.get("run_id", "run-1")},
            "detail": self.detail,
        }


def direct_state_trace(target: str, service: str, trigger_entity: str, before: str, after: str):
    domain = target.split(".", 1)[0]
    return {
        "run_id": "run-direct",
        "trigger": {
            "platform": "state",
            "entity_id": trigger_entity,
            "from": before,
            "to": after,
            "from_state": {"state": before},
            "to_state": {"state": after},
        },
        "trace": {
            "action/0": [
                {
                    "path": "action/0",
                    "result": {
                        "params": {
                            "domain": domain,
                            "service": service,
                            "target": {"entity_id": target},
                            "service_data": {},
                        }
                    },
                }
            ]
        },
    }


def wait_motion_trace(target: str):
    return {
        "run_id": "run-wait",
        "trigger": {
            "platform": "state",
            "entity_id": "binary_sensor.mouvement_sdb",
            "from": "off",
            "to": "on",
            "to_state": {"state": "on"},
        },
        "config": {
            "actions": [
                {"action": "light.turn_on", "target": {"entity_id": target}},
                {
                    "wait_for_trigger": [
                        {
                            "trigger": "state",
                            "entity_id": "binary_sensor.mouvement_sdb",
                            "to": "off",
                            "for": "00:05:00",
                        }
                    ]
                },
                {"action": "light.turn_off", "target": {"entity_id": target}},
            ]
        },
        "trace": {
            "action/0": [
                {
                    "path": "action/0",
                    "result": {
                        "params": {
                            "domain": "light",
                            "service": "turn_on",
                            "target": {"entity_id": target},
                            "service_data": {},
                        }
                    },
                }
            ],
            "action/1": [
                {
                    "path": "action/1",
                    "result": {
                        "wait": {
                            "completed": True,
                            "trigger": {
                                "platform": "state",
                                "entity_id": "binary_sensor.mouvement_sdb",
                                "to": "off",
                                "to_state": {"state": "off"},
                                "idx": "0",
                            },
                        }
                    },
                }
            ],
            "action/2": [
                {
                    "path": "action/2",
                    "result": {
                        "params": {
                            "domain": "light",
                            "service": "turn_off",
                            "target": {"entity_id": target},
                            "service_data": {},
                        }
                    },
                }
            ],
        },
    }


class TestDev37MemoryEnrichment(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3")

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    async def test_call_service_keeps_proven_automation_and_translates_terrace_contact(self):
        target = "light.lampe_terrasse"
        stored = self.recorder.record(
            CausalRecord(
                entity_id=target,
                entity_name="Lampe terrasse",
                event_time=iso(10),
                event_kind="turned_off",
                before_value="on",
                after_value="off",
                origin_type="automation",
                source_entity_id="automation.terrasse_extinction",
                source_name="Terrasse - Extinction fermeture ou lever du soleil",
                reason="state of binary_sensor.porte_fenetre_contact",
                confidence="confirmed",
                trigger={"effect_context_id": "ctx-terrasse"},
            )
        )
        ha = FakeHA(
            entries=[
                {
                    "when": iso(10),
                    "entity_id": target,
                    "state": "off",
                    "context_id": "ctx-terrasse",
                    "context_event_type": "call_service",
                    "context_domain": "light",
                    "context_service": "turn_off",
                }
            ],
            states={
                "binary_sensor.porte_fenetre_contact": {
                    "entity_id": "binary_sensor.porte_fenetre_contact",
                    "state": "off",
                    "attributes": {
                        "friendly_name": "Porte-fenêtre",
                        "device_class": "door",
                    },
                }
            },
        )
        traces = FakeTraceInvestigator(
            direct_state_trace(
                target,
                "turn_off",
                "binary_sensor.porte_fenetre_contact",
                "on",
                "off",
            )
        )
        enricher = TargetedMemoryEnricher(ha, traces).bind_recorder(self.recorder)

        self.assertTrue(await enricher.enrich([stored]))
        result = self.recorder.get(stored.record_id)
        self.assertEqual(result.origin_type, "automation")
        self.assertEqual(result.source_entity_id, "automation.terrasse_extinction")
        self.assertEqual(result.reason, "la porte-fenêtre a été refermée")
        self.assertNotIn("state of", result.reason)
        self.assertEqual(traces.calls, 1)

    async def test_wait_for_trigger_regression_keeps_no_motion_reason(self):
        target = "light.salle_de_bain"
        stored = self.recorder.record(
            CausalRecord(
                entity_id=target,
                entity_name="Lampe salle de bain",
                event_time=iso(305),
                event_kind="turned_off",
                before_value="on",
                after_value="off",
                origin_type="automation",
                source_entity_id="automation.salle_de_bain",
                source_name="Salle de bain",
                reason="state of binary_sensor.mouvement_sdb",
                confidence="confirmed",
                trigger={"effect_context_id": "ctx-sdb"},
            )
        )
        ha = FakeHA(
            entries=[
                {
                    "when": iso(305),
                    "entity_id": target,
                    "state": "off",
                    "context_id": "ctx-sdb",
                    "context_event_type": "call_service",
                    "context_domain": "light",
                    "context_service": "turn_off",
                }
            ],
            states={
                "binary_sensor.mouvement_sdb": {
                    "entity_id": "binary_sensor.mouvement_sdb",
                    "state": "off",
                    "attributes": {
                        "friendly_name": "Mouvement salle de bain",
                        "device_class": "motion",
                    },
                }
            },
        )
        traces = FakeTraceInvestigator(wait_motion_trace(target))
        enricher = TargetedMemoryEnricher(ha, traces).bind_recorder(self.recorder)

        self.assertTrue(await enricher.enrich([stored]))
        result = self.recorder.get(stored.record_id)
        self.assertEqual(result.origin_type, "automation")
        self.assertEqual(result.reason, "il n'y avait plus de mouvement")
        self.assertEqual(result.trace_run_id, "run-wait")

    async def test_cover_terminal_inherits_exact_same_movement_cause(self):
        start = self.recorder.record(
            CausalRecord(
                entity_id="cover.volet_terrasse_2",
                entity_name="Volet terrasse",
                event_time=iso(10),
                event_kind="closing",
                before_value="open",
                after_value="closing",
                origin_type="automation",
                source_entity_id="automation.fermer_volet_terrasse",
                source_name="Fermer volet terrasse",
                reason="la porte-fenêtre a été refermée",
                confidence="confirmed",
                trigger={"effect_context_id": "ctx-start"},
                trace_run_id="run-cover",
            )
        )
        terminal = self.recorder.record(
            CausalRecord(
                entity_id="cover.volet_terrasse_2",
                entity_name="Volet terrasse",
                event_time=iso(22),
                event_kind="closed",
                before_value="closing",
                after_value="closed",
                origin_type="unknown",
                confidence="confirmed",
                trigger={"effect_context_id": "ctx-terminal"},
            )
        )
        enricher = TargetedMemoryEnricher(ExplodingHA(), FakeTraceInvestigator({})).bind_recorder(
            self.recorder
        )

        self.assertTrue(await enricher.enrich([terminal]))
        result = self.recorder.get(terminal.record_id)
        self.assertEqual(result.origin_type, "automation")
        self.assertEqual(result.reason, "la porte-fenêtre a été refermée")
        self.assertEqual(result.trace_run_id, "run-cover")
        self.assertEqual(result.reason_code, "cover_episode_continuity")
        self.assertEqual(result.trigger["cover_episode"]["source_record_id"], start.record_id)

    async def test_cover_terminal_never_inherits_opposite_direction(self):
        self.recorder.record(
            CausalRecord(
                entity_id="cover.volet_terrasse_2",
                entity_name="Volet terrasse",
                event_time=iso(10),
                event_kind="opening",
                before_value="closed",
                after_value="opening",
                origin_type="automation",
                source_entity_id="automation.ouvrir_volet_terrasse",
                reason="la porte-fenêtre a été ouverte",
                confidence="confirmed",
            )
        )
        terminal = self.recorder.record(
            CausalRecord(
                entity_id="cover.volet_terrasse_2",
                entity_name="Volet terrasse",
                event_time=iso(20),
                event_kind="closed",
                before_value="closing",
                after_value="closed",
                origin_type="unknown",
                confidence="confirmed",
                trigger={"effect_context_id": "ctx-terminal"},
            )
        )
        ha = FakeHA(entries=[])
        enricher = TargetedMemoryEnricher(ha, FakeTraceInvestigator({})).bind_recorder(self.recorder)

        self.assertFalse(await enricher.enrich([terminal]))
        result = self.recorder.get(terminal.record_id)
        self.assertEqual(result.origin_type, "unknown")
        self.assertIsNone(result.reason)

    async def test_dev37_context_horizon_accepts_effect_just_after_five_minutes(self):
        old_pending = memory_base._PENDING_SECONDS
        try:
            configure_dev37()
            worker = ConsciousMemoryWorker(None, self.recorder)
            worker._capture_automation(
                {
                    "event_type": "automation_triggered",
                    "time_fired": iso(0),
                    "data": {
                        "entity_id": "automation.hotte_mouvement",
                        "name": "Hotte mouvement",
                        "source": "state of binary_sensor.hue_motion_sensor_1_mouvement",
                    },
                    "context": {"id": "ctx-hotte", "parent_id": None, "user_id": None},
                }
            )
            change = ObservedChange(
                entity_id="light.hotte",
                entity_name="Hotte",
                event_time=iso(301),
                event_kind="turned_off",
                before_value="on",
                after_value="off",
                attribute=None,
                context_id="ctx-hotte",
                parent_id=None,
                user_id=None,
                domain="light",
            )
            trigger = worker._find_trigger(change, None)
            self.assertIsNotNone(trigger)
            self.assertEqual(trigger.entity_id, "automation.hotte_mouvement")
            self.assertGreater(memory_base._PENDING_SECONDS, 301)
        finally:
            memory_base._PENDING_SECONDS = old_pending


if __name__ == "__main__":
    unittest.main()
