from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_v2 import _cover_partial_episode_carrier
from causal_renderer_v2 import CausalRendererV2
from cover_cause_v2 import cover_branch_numeric_factors, periodic_position_decision
from models import Evidence, InvestigationResult


class _HA:
    async def get_state(self, entity_id):
        attrs = {}
        if entity_id == "sensor.temperature_exterieure":
            attrs = {"friendly_name": "Température extérieure", "unit_of_measurement": "°C"}
        elif entity_id == "sensor.eclairement":
            attrs = {"friendly_name": "Éclairement", "unit_of_measurement": "lx"}
        elif entity_id == "sun.sun":
            attrs = {"friendly_name": "Soleil"}
        return {"entity_id": entity_id, "attributes": attrs}


def _entry(state, when, *, source=None, name=None, user=None):
    return {
        "entity_id": "cover.volet_salon_2",
        "state": state,
        "when": when,
        "context_entity_id": source,
        "context_entity_id_name": name,
        "context_user_id": user,
    }


def _result_with_trace(detail):
    return InvestigationResult(
        status="confirmed",
        entity_id="cover.volet_salon_2",
        entity_name="volet salon",
        event_type="opened",
        event_time="2026-09-12T11:10:15+00:00",
        observed={"after": "open"},
        cause={"type": "automation", "system_confirmed": True},
        evidence=[
            Evidence(
                kind="trace",
                summary="trace",
                source="automation.test",
                strength="direct",
                raw=detail,
            )
        ],
    )


class CoverEpisodeV2Tests(unittest.IsolatedAsyncioTestCase):
    def test_partial_closing_to_open_borrows_adjacent_automation_context(self):
        terminal = _entry("open", "2026-09-12T10:42:59+00:00")
        movement = _entry(
            "closing",
            "2026-09-12T10:42:46+00:00",
            source="automation.gestion_volet_salon_avec_soleil_et_saison",
            name="Gestion volet salon avec soleil et saison",
        )
        carrier = _cover_partial_episode_carrier(
            terminal,
            [terminal, movement],
            "cover.volet_salon_2",
        )
        self.assertIs(carrier, movement)

    def test_closed_terminal_never_borrows_opening_row(self):
        terminal = _entry("closed", "2026-09-12T10:42:59+00:00")
        movement = _entry(
            "opening",
            "2026-09-12T10:42:46+00:00",
            source="automation.test",
            name="Automation test",
        )
        carrier = _cover_partial_episode_carrier(
            terminal,
            [terminal, movement],
            "cover.volet_salon_2",
        )
        self.assertIs(carrier, terminal)

    def test_non_cover_is_never_touched(self):
        terminal = {"entity_id": "light.test", "state": "on", "when": "2026-09-12T10:00:01+00:00"}
        movement = {"entity_id": "light.test", "state": "off", "when": "2026-09-12T10:00:00+00:00", "context_entity_id": "automation.test"}
        carrier = _cover_partial_episode_carrier(terminal, [terminal, movement], "light.test")
        self.assertIs(carrier, terminal)

    async def test_periodic_cover_position_fallback_is_unchanged_without_branch_evidence(self):
        result = InvestigationResult(
            status="confirmed",
            entity_id="cover.volet_salon_2",
            entity_name="volet salon",
            event_type="opened",
            event_time="2026-09-12T11:10:15+00:00",
            observed={"after": "open"},
            cause={"type": "automation", "system_confirmed": True},
            evidence=[],
        )
        trigger = {"platform": "time_pattern", "minutes": "/10"}
        command = {
            "path": "action/4/choose/0/sequence/0",
            "domain": "cover",
            "service": "set_cover_position",
            "data": {"position": 100},
        }
        cause = periodic_position_decision(result, command, trigger)
        self.assertIsNotNone(cause)
        self.assertEqual(cause["detail"]["requested_position"], 100.0)
        self.assertEqual(cause["detail"]["decision_factors"], [])
        renderer = CausalRendererV2(_HA())
        text = await renderer.render(cause)
        self.assertEqual(
            text,
            "le contrôle périodique toutes les 10 minutes s'est déclenché et l'automatisation a demandé la position 100 %",
        )

    async def test_temperature_factor_is_rendered_and_state_guard_is_not_promoted(self):
        detail = {
            "config": {
                "actions": [
                    {}, {}, {}, {},
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {
                                        "condition": "numeric_state",
                                        "entity_id": "sensor.temperature_exterieure",
                                        "above": 25,
                                    },
                                    {
                                        "condition": "state",
                                        "entity_id": "binary_sensor.fenetre_salon",
                                        "state": "off",
                                    },
                                ],
                                "sequence": [
                                    {
                                        "action": "cover.set_cover_position",
                                        "target": {"entity_id": "cover.volet_salon_2"},
                                        "data": {"position": 80},
                                    }
                                ],
                            }
                        ]
                    },
                ]
            },
            "trace": {
                "action/4/choose/0": [{"result": {"result": True}}],
                "action/4/choose/0/conditions/0": [{"result": {"result": True, "state": 27.4}}],
                "action/4/choose/0/conditions/1": [{"result": {"result": True, "state": "off"}}],
            },
        }
        result = _result_with_trace(detail)
        command = {
            "path": "action/4/choose/0/sequence/0",
            "domain": "cover",
            "service": "set_cover_position",
            "data": {"position": 80},
        }
        factors = cover_branch_numeric_factors(result, command)
        self.assertEqual(len(factors), 1)
        self.assertEqual(factors[0]["entity_id"], "sensor.temperature_exterieure")
        self.assertEqual(factors[0]["above"], 25)
        self.assertNotIn("binary_sensor.fenetre_salon", str(factors))

        cause = periodic_position_decision(
            result,
            command,
            {"platform": "time_pattern", "minutes": "/10"},
        )
        text = await CausalRendererV2(_HA()).render(cause)
        self.assertEqual(
            text,
            "la température extérieure dépassait 25 °C; lors du contrôle périodique, l'automatisation a demandé la position 80 %",
        )

    async def test_solar_position_and_lux_numeric_factors_are_rendered_from_exact_branch(self):
        detail = {
            "config": {
                "actions": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {
                                        "condition": "numeric_state",
                                        "entity_id": "sun.sun",
                                        "attribute": "azimuth",
                                        "above": 54,
                                        "below": 165,
                                    },
                                    {
                                        "condition": "numeric_state",
                                        "entity_id": "sun.sun",
                                        "attribute": "elevation",
                                        "above": 0,
                                    },
                                    {
                                        "condition": "numeric_state",
                                        "entity_id": "sensor.eclairement",
                                        "above": 15000,
                                    },
                                ],
                                "sequence": [
                                    {
                                        "action": "cover.set_cover_position",
                                        "target": {"entity_id": "cover.volet_salon_2"},
                                        "data": {"position": 30},
                                    }
                                ],
                            }
                        ]
                    }
                ]
            },
            "trace": {
                "action/0/choose/0": [{"result": {"result": True}}],
                "action/0/choose/0/conditions/0": [{"result": {"result": True, "state": 120}}],
                "action/0/choose/0/conditions/1": [{"result": {"result": True, "state": 41}}],
                "action/0/choose/0/conditions/2": [{"result": {"result": True, "state": 22000}}],
            },
        }
        result = _result_with_trace(detail)
        command = {
            "path": "action/0/choose/0/sequence/0",
            "domain": "cover",
            "service": "set_cover_position",
            "data": {"position": 30},
        }
        cause = periodic_position_decision(
            result,
            command,
            {"platform": "time_pattern", "minutes": "/10"},
        )
        self.assertEqual(len(cause["detail"]["decision_factors"]), 3)
        text = await CausalRendererV2(_HA()).render(cause)
        self.assertIn("l’azimut solaire était compris entre 54° et 165°", text)
        self.assertIn("l’élévation solaire dépassait 0°", text)
        self.assertIn("Éclairement", text)
        self.assertIn("15000 lx", text)
        self.assertIn("position 30 %", text)

    def test_periodic_position_extension_refuses_switches(self):
        result = InvestigationResult(
            status="confirmed",
            entity_id="switch.test",
            entity_name="switch test",
            event_type="turned_on",
            event_time="2026-09-12T11:10:15+00:00",
            observed={"after": "on"},
            cause={"type": "automation", "system_confirmed": True},
            evidence=[],
        )
        cause = periodic_position_decision(
            result,
            {"domain": "switch", "service": "turn_on", "data": {}},
            {"platform": "time_pattern", "minutes": "/10"},
        )
        self.assertIsNone(cause)


if __name__ == "__main__":
    unittest.main()
