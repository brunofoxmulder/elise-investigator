from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from activity_reader_dev59 import select_activity_entry


class TestDev59ActivityFirst(unittest.TestCase):
    def test_light_uses_activity_state_not_brightness_memory_noise(self):
        entries = [
            {
                "entity_id": "light.salon",
                "when": "2026-09-06T17:50:56+00:00",
                "state": "on",
                "context_entity_id": "automation.ambiance_du_soir",
                "context_entity_id_name": "Ambiance du soir",
            },
            {
                "entity_id": "light.salon",
                "when": "2026-09-06T17:40:16+00:00",
                "state": "off",
                "context_user_id": "user-1",
            },
        ]
        selected = select_activity_entry(entries, "light.salon")
        self.assertEqual(selected["state"], "on")
        self.assertEqual(selected["context_entity_id"], "automation.ambiance_du_soir")

    def test_cover_terminal_row_reuses_same_activity_episode_attribution(self):
        entries = [
            {
                "entity_id": "cover.volet_salon",
                "when": "2026-09-06T19:06:18+00:00",
                "state": "closed",
            },
            {
                "entity_id": "cover.volet_salon",
                "when": "2026-09-06T19:06:05+00:00",
                "state": "closing",
                "context_entity_id": "automation.gestion_volet_salon",
                "context_entity_id_name": "Gestion volet salon",
            },
        ]
        selected = select_activity_entry(entries, "cover.volet_salon")
        self.assertEqual(selected["state"], "closing")
        self.assertEqual(selected["context_entity_id"], "automation.gestion_volet_salon")

    def test_unknown_unavailable_are_ignored(self):
        entries = [
            {"entity_id": "switch.tineco", "when": "2026-09-06T18:03:00+00:00", "state": "unavailable"},
            {"entity_id": "switch.tineco", "when": "2026-09-06T18:02:00+00:00", "state": "off", "context_entity_id": "automation.charge_tineco"},
        ]
        selected = select_activity_entry(entries, "switch.tineco")
        self.assertEqual(selected["state"], "off")


if __name__ == "__main__":
    unittest.main()
