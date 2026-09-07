from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord, CausalRecorder
from memory_selection_dev58 import find_best_functional


class TestDev58FunctionalStateSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # These tests validate selection semantics, not retention pruning. Keep a
        # wider window so fixed terrain timestamps remain deterministic over time.
        self.recorder = CausalRecorder(Path(self.tmp.name) / "memory.sqlite3", retention_hours=72)

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    def test_plain_light_question_ignores_later_brightness_change(self):
        self.recorder.record(CausalRecord(
            entity_id="light.hue_tento_color_panel_1_3",
            entity_name="lampe salon",
            event_time="2026-09-06T17:50:56+00:00",
            event_kind="turned_on",
            before_value="off",
            after_value="on",
            origin_type="automation",
            source_entity_id="automation.ambiance_du_soir",
            source_name="Ambiance du soir - Allumage",
            reason="l'automatisation Ambiance du soir s'est déclenchée",
            confidence="confirmed",
        ), now=None)
        self.recorder.record(CausalRecord(
            entity_id="light.hue_tento_color_panel_1_3",
            entity_name="lampe salon",
            event_time="2026-09-06T17:59:49+00:00",
            event_kind="brightness_changed",
            before_value=45,
            after_value=46,
            attribute="brightness",
            origin_type="unknown",
            confidence="confirmed",
        ), now=None)

        item = find_best_functional(self.recorder, "light.hue_tento_color_panel_1_3")
        self.assertIsNotNone(item)
        self.assertEqual(item.event_kind, "turned_on")
        self.assertEqual(item.event_time, "2026-09-06T17:50:56+00:00")
        self.assertEqual(item.origin_type, "automation")

    def test_explicit_brightness_question_keeps_existing_semantics(self):
        self.recorder.record(CausalRecord(
            entity_id="light.test",
            event_time="2026-09-06T17:50:00+00:00",
            event_kind="turned_on",
            before_value="off",
            after_value="on",
            origin_type="user",
            confidence="confirmed",
        ))
        self.recorder.record(CausalRecord(
            entity_id="light.test",
            event_time="2026-09-06T17:55:00+00:00",
            event_kind="brightness_changed",
            before_value=40,
            after_value=45,
            attribute="brightness",
            origin_type="unknown",
            confidence="confirmed",
        ))

        item = find_best_functional(self.recorder, "light.test", attribute="brightness")
        self.assertIsNotNone(item)
        self.assertEqual(item.event_kind, "brightness_changed")
        self.assertEqual(item.after_value, 45)

    def test_non_light_entities_use_existing_selection(self):
        self.recorder.record(CausalRecord(
            entity_id="cover.volet_salon_2",
            event_time="2026-09-06T17:50:00+00:00",
            event_kind="closed",
            before_value="closing",
            after_value="closed",
            origin_type="automation",
            reason="fermeture solaire",
            confidence="confirmed",
        ))
        item = find_best_functional(self.recorder, "cover.volet_salon_2")
        self.assertIsNotNone(item)
        self.assertEqual(item.event_kind, "closed")


if __name__ == "__main__":
    unittest.main()
