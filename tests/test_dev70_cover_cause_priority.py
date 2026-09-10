from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_dev70 import _functional_entries
from causal_recorder import CausalRecord
from targeted_memory_enricher_dev70 import TargetedMemoryEnricher


class _HA:
    async def get_state(self, entity_id):
        names = {
            "sensor.temperature_exterieure": ("Température extérieure", "°C"),
            "sensor.telephone_battery": ("Téléphone Battery level", "%"),
            "binary_sensor.rte_tempo_heures_creuses": ("Heures creuses", None),
        }
        name, unit = names.get(entity_id, (entity_id, None))
        attrs = {"friendly_name": name}
        if unit:
            attrs["unit_of_measurement"] = unit
        return {"entity_id": entity_id, "state": "on", "attributes": attrs}


class _TraceInvestigator:
    pass


def _nested_detail(*, trigger_platform="time_pattern", trigger_entity=None):
    trigger = {"platform": trigger_platform}
    if trigger_entity:
        trigger.update({
            "entity_id": trigger_entity,
            "from_state": {"state": "off"},
            "to_state": {"state": "on"},
        })
    return {
        "config": {
            "actions": [
                {
                    "choose": [
                        {
                            "conditions": [{
                                "condition": "state",
                                "entity_id": "input_boolean.enabled",
                                "state": "on",
                            }],
                            "sequence": [
                                {
                                    "choose": [
                                        {
                                            "conditions": [{
                                                "condition": "numeric_state",
                                                "entity_id": "sensor.temperature_exterieure" if trigger_platform == "time_pattern" else "sensor.telephone_battery",
                                                "above": 28 if trigger_platform == "time_pattern" else None,
                                                "below": None if trigger_platform == "time_pattern" else 50,
                                            }],
                                            "sequence": [{
                                                "action": "cover.open_cover" if trigger_platform == "time_pattern" else "switch.turn_on",
                                                "target": {"entity_id": "cover.volet_salon_2" if trigger_platform == "time_pattern" else "switch.chargeur_telephone_2"},
                                            }],
                                        }
                                    ]
                                }
                            ],
                        }
                    ]
                }
            ]
        },
        "trace": {
            "trigger/0": [{"changed_variables": {"trigger": trigger}}],
            "action/0": [{"result": {"choice": 0}}],
            "action/0/choose/0": [{"result": {"result": True}}],
            "action/0/choose/0/conditions/0": [{"result": {"result": True, "state": "on"}}],
            "action/0/choose/0/sequence/0": [{"result": {"choice": 0}}],
            "action/0/choose/0/sequence/0/choose/0": [{"result": {"result": True}}],
            "action/0/choose/0/sequence/0/choose/0/conditions/0": [{
                "result": {
                    "result": True,
                    "state": 29.4 if trigger_platform == "time_pattern" else 35,
                }
            }],
            "action/0/choose/0/sequence/0/choose/0/sequence/0": [{
                "result": {
                    "params": {
                        "domain": "cover" if trigger_platform == "time_pattern" else "switch",
                        "service": "open_cover" if trigger_platform == "time_pattern" else "turn_on",
                        "target": {"entity_id": ["cover.volet_salon_2" if trigger_platform == "time_pattern" else "switch.chargeur_telephone_2"]},
                        "service_data": {},
                    }
                }
            }],
        },
    }


class Dev70Tests(unittest.IsolatedAsyncioTestCase):
    def test_same_state_refresh_is_removed_when_real_boundary_is_visible(self):
        entries = [
            {"entity_id": "cover.volet_salon_2", "state": "open", "when": "2026-09-10T11:01:00+00:00"},
            {"entity_id": "cover.volet_salon_2", "state": "open", "when": "2026-09-10T11:00:16+00:00"},
            {"entity_id": "cover.volet_salon_2", "state": "opening", "when": "2026-09-10T11:00:10+00:00", "context_entity_id": "automation.gestion_volet_salon_avec_soleil_et_saison"},
            {"entity_id": "cover.volet_salon_2", "state": "closed", "when": "2026-09-10T10:00:00+00:00"},
        ]
        filtered = _functional_entries(entries, "cover.volet_salon_2")
        states = [entry["state"] for entry in filtered]
        self.assertEqual(states, ["open", "opening", "closed"])
        self.assertEqual(filtered[0]["when"], "2026-09-10T11:00:16+00:00")

    def test_no_visible_state_boundary_keeps_activity_unchanged(self):
        entries = [
            {"entity_id": "cover.volet_salon_2", "state": "open", "when": "2026-09-10T11:01:00+00:00"},
            {"entity_id": "cover.volet_salon_2", "state": "open", "when": "2026-09-10T11:00:16+00:00"},
        ]
        self.assertEqual(_functional_entries(entries, "cover.volet_salon_2"), entries)

    async def test_nested_temperature_branch_beats_time_pattern(self):
        helper = TargetedMemoryEnricher(_HA(), _TraceInvestigator())
        record = CausalRecord(
            entity_id="cover.volet_salon_2",
            event_time="2026-09-10T11:00:16+00:00",
            event_kind="opened",
            after_value="open",
            origin_type="automation",
            source_entity_id="automation.gestion_volet_salon_avec_soleil_et_saison",
            source_name="Gestion volet salon avec soleil et saison",
            confidence="confirmed",
        )
        reason, _, cause = await helper._reason_from_detail(
            record,
            record.source_entity_id,
            record.source_name,
            "automation",
            _nested_detail(),
            "run-cover",
        )
        self.assertIsNotNone(reason)
        self.assertNotIn("time pattern", reason.lower())
        self.assertIn("température extérieure", reason.lower())
        self.assertEqual(cause["origin"], "executed_branch_conditions")

    async def test_state_trigger_can_join_proven_nested_battery_condition(self):
        detail = _nested_detail(
            trigger_platform="state",
            trigger_entity="binary_sensor.rte_tempo_heures_creuses",
        )
        # Remove the outer unrelated guard: the exact command path then proves only the
        # low-battery branch condition in addition to the start trigger.
        detail["config"]["actions"][0]["choose"][0]["conditions"] = []
        detail["trace"].pop("action/0/choose/0/conditions/0")

        helper = TargetedMemoryEnricher(_HA(), _TraceInvestigator())
        record = CausalRecord(
            entity_id="switch.chargeur_telephone_2",
            event_time="2026-09-10T20:30:26+00:00",
            event_kind="turned_on",
            after_value="on",
            origin_type="automation",
            source_entity_id="automation.charge_s20_sur_prise_intelligente_1_heure_creuse",
            source_name="Charge S20 sur prise intelligente 1 heure creuse",
            confidence="confirmed",
        )
        reason, _, cause = await helper._reason_from_detail(
            record,
            record.source_entity_id,
            record.source_name,
            "automation",
            detail,
            "run-phone",
        )
        self.assertIsNotNone(reason)
        self.assertIn("et", reason)
        self.assertEqual(cause["origin"], "trigger_plus_conditions")


if __name__ == "__main__":
    unittest.main()
