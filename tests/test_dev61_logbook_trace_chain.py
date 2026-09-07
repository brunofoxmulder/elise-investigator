from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_dev61 import ActivityTraceReader


class _HA:
    def __init__(self, mapping, states=None):
        self.mapping = mapping
        self.states = states or {}

    async def get_logbook(self, entity_id, start, end):
        return list(self.mapping.get(entity_id, []))

    async def get_state(self, entity_id):
        return self.states.get(entity_id, {"attributes": {}})


class _TraceInvestigator:
    pass


class TestDev61LogbookTraceChain(unittest.IsolatedAsyncioTestCase):
    async def test_cover_terminal_keeps_closed_fact_and_uses_closing_automation(self):
        entries = {
            "cover.volet_salon_2": [
                {
                    "entity_id": "cover.volet_salon_2",
                    "when": "2026-09-07T13:20:22+00:00",
                    "state": "closed",
                },
                {
                    "entity_id": "cover.volet_salon_2",
                    "when": "2026-09-07T13:20:01+00:00",
                    "state": "closing",
                    "context_entity_id": "automation.gestion_volet_salon_avec_soleil_et_saison",
                    "context_entity_id_name": "Gestion volet salon avec soleil et saison",
                    "context_source": "time pattern",
                },
            ]
        }
        reader = ActivityTraceReader(_HA(entries), _TraceInvestigator())
        reader.trace_helper._trace_reason = AsyncMock(
            return_value=("la température extérieure était supérieure à 28 °C", "run-volet", {"kind": "condition"})
        )
        record = await reader.investigate("cover.volet_salon_2")
        self.assertEqual(record.event_kind, "closed")
        self.assertEqual(record.after_value, "closed")
        self.assertEqual(record.origin_type, "automation")
        self.assertEqual(record.source_entity_id, "automation.gestion_volet_salon_avec_soleil_et_saison")
        self.assertEqual(record.reason, "la température extérieure était supérieure à 28 °C")
        self.assertEqual(record.reason_code, "ha_logbook+exact_trace")

    async def test_manual_cover_close_does_not_borrow_old_automation(self):
        entries = {
            "cover.volet_salon_2": [
                {
                    "entity_id": "cover.volet_salon_2",
                    "when": "2026-09-07T14:00:10+00:00",
                    "state": "closed",
                    "context_user_id": "user-1",
                },
                {
                    "entity_id": "cover.volet_salon_2",
                    "when": "2026-09-07T13:20:01+00:00",
                    "state": "closing",
                    "context_entity_id": "automation.gestion_volet_salon_avec_soleil_et_saison",
                },
            ]
        }
        reader = ActivityTraceReader(_HA(entries), _TraceInvestigator())
        reader.trace_helper._trace_reason = AsyncMock(return_value=(None, None, None))
        record = await reader.investigate("cover.volet_salon_2")
        self.assertEqual(record.origin_type, "user")
        self.assertIsNone(record.source_entity_id)

    async def test_kitchen_light_can_follow_one_explicit_trace_hop_to_cover_reason(self):
        mapping = {
            "light.lampe_cuisine": [
                {
                    "entity_id": "light.lampe_cuisine",
                    "when": "2026-09-07T13:20:22.569177+00:00",
                    "state": "on",
                    "context_entity_id": "automation.ambiance_du_jour_fermeture_volets_jour",
                    "context_entity_id_name": "Ambiance du jour fermeture volets jour",
                    "context_source": "state of cover.volet_salon_2",
                }
            ],
            "cover.volet_salon_2": [
                {
                    "entity_id": "cover.volet_salon_2",
                    "when": "2026-09-07T13:20:22.261882+00:00",
                    "state": "closed",
                },
                {
                    "entity_id": "cover.volet_salon_2",
                    "when": "2026-09-07T13:20:01+00:00",
                    "state": "closing",
                    "context_entity_id": "automation.gestion_volet_salon_avec_soleil_et_saison",
                    "context_entity_id_name": "Gestion volet salon avec soleil et saison",
                },
            ],
        }
        states = {
            "cover.volet_salon_2": {"attributes": {"friendly_name": "volet salon"}},
        }
        reader = ActivityTraceReader(_HA(mapping, states), _TraceInvestigator())

        async def trace_reason(record, source_entity_id, source_name, source_kind):
            if source_entity_id == "automation.ambiance_du_jour_fermeture_volets_jour":
                return (
                    "le volet salon est passé à fermé",
                    "run-lampe",
                    {"kind": "trigger", "detail": {"entity_id": "cover.volet_salon_2", "to": "closed"}},
                )
            if source_entity_id == "automation.gestion_volet_salon_avec_soleil_et_saison":
                return (
                    "la température extérieure était supérieure à 28 °C",
                    "run-volet",
                    {"kind": "condition"},
                )
            return (None, None, None)

        reader.trace_helper._trace_reason = AsyncMock(side_effect=trace_reason)
        record = await reader.investigate("light.lampe_cuisine")
        self.assertEqual(record.origin_type, "automation")
        self.assertEqual(record.source_entity_id, "automation.ambiance_du_jour_fermeture_volets_jour")
        self.assertIn("le volet salon est passé à fermé", record.reason)
        self.assertIn("volet salon s'est fermé parce que la température extérieure était supérieure à 28 °C", record.reason)
        self.assertEqual(record.reason_code, "ha_logbook+exact_trace+one_native_hop")
        self.assertIn("upstream", record.trigger)

    async def test_tineco_keeps_simple_native_source_if_trace_adds_nothing(self):
        mapping = {
            "switch.tineco": [
                {
                    "entity_id": "switch.tineco",
                    "when": "2026-09-07T10:00:00+00:00",
                    "state": "off",
                    "context_entity_id": "automation.couper_prise_tineco_quand_charge_terminee",
                    "context_entity_id_name": "Couper prise Tineco quand charge terminée",
                    "context_source": "numeric state of sensor.tineco_battery",
                }
            ]
        }
        reader = ActivityTraceReader(_HA(mapping), _TraceInvestigator())
        reader.trace_helper._trace_reason = AsyncMock(return_value=(None, None, None))
        record = await reader.investigate("switch.tineco")
        self.assertEqual(record.reason, "numeric state of sensor.tineco_battery")
        self.assertEqual(record.reason_code, "ha_2026_9_activity_source_hint")


if __name__ == "__main__":
    unittest.main()
