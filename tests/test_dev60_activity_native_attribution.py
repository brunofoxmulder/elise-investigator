from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_dev60 import ActivityFirstReader, _origin, select_activity_entry


class _HA:
    def __init__(self, entries):
        self.entries = entries

    async def get_logbook(self, entity_id, start, end):
        return list(self.entries)


class _TraceInvestigator:
    pass


class TestDev60ActivityNativeAttribution(unittest.IsolatedAsyncioTestCase):
    def test_chargeur_casque_activity_automation_beats_inherited_user_context(self):
        origin, source, name = _origin(
            {
                "context_user_id": "user-1",
                "context_entity_id": "automation.bonne_nuit",
                "context_entity_id_name": "Bonne nuit",
            }
        )
        self.assertEqual(origin, "automation")
        self.assertEqual(source, "automation.bonne_nuit")
        self.assertEqual(name, "Bonne nuit")

    def test_volet_terminal_fact_is_never_replaced_by_closing(self):
        entries = [
            {
                "entity_id": "cover.volet_salon_2",
                "when": "2026-09-06T19:06:18+00:00",
                "state": "closed",
            },
            {
                "entity_id": "cover.volet_salon_2",
                "when": "2026-09-06T19:06:05+00:00",
                "state": "closing",
                "context_entity_id": "automation.fermeture_volet",
            },
        ]
        selected = select_activity_entry(entries, "cover.volet_salon_2")
        self.assertEqual(selected["state"], "closed")
        self.assertEqual(selected["when"], "2026-09-06T19:06:18+00:00")

    async def test_tineco_native_source_survives_when_trace_adds_nothing(self):
        entries = [
            {
                "entity_id": "switch.tineco",
                "when": "2026-09-06T18:35:13+00:00",
                "state": "off",
                "context_entity_id": "automation.couper_prise_tineco_quand_charge_terminee",
                "context_entity_id_name": "Couper prise Tineco quand charge terminée",
                "context_source": "numeric state of sensor.tineco_battery",
            }
        ]
        reader = ActivityFirstReader(_HA(entries), _TraceInvestigator())
        reader.trace_helper._trace_reason = AsyncMock(return_value=(None, None, None))
        record = await reader.investigate("switch.tineco")
        self.assertEqual(record.reason, "numeric state of sensor.tineco_battery")
        self.assertEqual(record.reason_code, "ha_2026_9_activity_source_hint")

    async def test_aspirateur_exact_trace_beats_automation_trigger_context(self):
        entries = [
            {
                "entity_id": "switch.prise_aspirateur",
                "when": "2026-09-06T20:02:06+00:00",
                "state": "off",
                "context_entity_id": "automation.charge_aspirateur",
                "context_entity_id_name": "Charge aspirateur",
                "context_source": "state of binary_sensor.rte_tempo_heures_creuses",
            }
        ]
        reader = ActivityFirstReader(_HA(entries), _TraceInvestigator())
        reader.trace_helper._trace_reason = AsyncMock(
            return_value=("la branche d'arrêt de cette exécution a été satisfaite", "run-asp", {"kind": "condition"})
        )
        record = await reader.investigate("switch.prise_aspirateur")
        self.assertEqual(record.reason, "la branche d'arrêt de cette exécution a été satisfaite")
        self.assertEqual(record.reason_code, "ha_activity+targeted_trace_detail")
        self.assertEqual(record.trace_run_id, "run-asp")

    async def test_volet_time_pattern_is_trigger_hint_not_final_reason_when_trace_explains_action(self):
        entries = [
            {
                "entity_id": "cover.volet_salon_2",
                "when": "2026-09-07T08:40:04+00:00",
                "state": "open",
                "context_entity_id": "automation.gestion_volet_salon_avec_soleil_et_saison",
                "context_entity_id_name": "Gestion volet salon avec soleil et saison",
                "context_source": "time pattern",
            }
        ]
        reader = ActivityFirstReader(_HA(entries), _TraceInvestigator())
        reader.trace_helper._trace_reason = AsyncMock(
            return_value=("les conditions de la branche d'ouverture étaient remplies", "run-volet", {"kind": "choose"})
        )
        record = await reader.investigate("cover.volet_salon_2")
        self.assertEqual(record.event_kind, "opened")
        self.assertEqual(record.reason, "les conditions de la branche d'ouverture étaient remplies")
        self.assertNotEqual(record.reason, "time pattern")

    async def test_context_link_can_supply_attribution_without_replacing_terminal_fact(self):
        entries = [
            {
                "entity_id": "cover.volet_salon_2",
                "when": "2026-09-06T19:06:18+00:00",
                "state": "closed",
                "context_parent_id": "ctx-automation",
            },
            {
                "entity_id": "cover.volet_salon_2",
                "when": "2026-09-06T19:06:05+00:00",
                "state": "closing",
                "context_id": "ctx-automation",
                "context_entity_id": "automation.fermeture_volet",
                "context_entity_id_name": "Fermeture volet",
            },
        ]
        reader = ActivityFirstReader(_HA(entries), _TraceInvestigator())
        reader.trace_helper._trace_reason = AsyncMock(return_value=(None, None, None))
        record = await reader.investigate("cover.volet_salon_2")
        self.assertEqual(record.event_kind, "closed")
        self.assertEqual(record.after_value, "closed")
        self.assertEqual(record.origin_type, "automation")
        self.assertEqual(record.source_entity_id, "automation.fermeture_volet")


if __name__ == "__main__":
    unittest.main()
