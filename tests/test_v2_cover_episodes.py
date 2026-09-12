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
from cover_cause_v2 import periodic_position_decision
from models import InvestigationResult


class _HA:
    async def get_state(self, entity_id):
        return {"entity_id": entity_id, "attributes": {}}


def _entry(state, when, *, source=None, name=None, user=None):
    return {
        "entity_id": "cover.volet_salon_2",
        "state": state,
        "when": when,
        "context_entity_id": source,
        "context_entity_id_name": name,
        "context_user_id": user,
    }


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

    async def test_periodic_cover_position_is_rendered_without_promoting_guards(self):
        result = InvestigationResult(
            status="confirmed",
            entity_id="cover.volet_salon_2",
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
        renderer = CausalRendererV2(_HA())
        text = await renderer.render(cause)
        self.assertEqual(
            text,
            "le contrôle périodique toutes les 10 minutes s'est déclenché et l'automatisation a demandé la position 100 %",
        )

    def test_periodic_position_extension_refuses_switches(self):
        result = InvestigationResult(
            status="confirmed",
            entity_id="switch.test",
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
