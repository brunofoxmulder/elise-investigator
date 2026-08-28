import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from causal_recorder import CausalRecord
from causal_recorder_dev33 import RelevantCausalRecorder


class TestDev33JournalSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "causal.sqlite3"
        self.now = datetime(2026, 8, 28, 17, 22, 33, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def _record_light_off_plus_brightness(self, recorder):
        # Same HA state_changed: primary state is captured first, controlled
        # attribute second, therefore the attribute gets the larger SQLite id.
        recorder.record(
            CausalRecord(
                entity_id="light.salle_de_bain",
                entity_name="Lampe salle de bain",
                event_time=self.now.isoformat(),
                event_kind="turned_off",
                before_value="on",
                after_value="off",
                attribute=None,
                origin_type="automation",
                reason="il n'y avait plus de mouvement",
                confidence="confirmed",
            ),
            now=self.now,
        )
        recorder.record(
            CausalRecord(
                entity_id="light.salle_de_bain",
                entity_name="Lampe salle de bain",
                event_time=self.now.isoformat(),
                event_kind="brightness_changed",
                before_value=180,
                after_value=0,
                attribute="brightness",
                origin_type="unknown",
                confidence="indeterminate",
            ),
            now=self.now,
        )

    def test_entity_only_lookup_prefers_primary_state_not_later_attribute_row(self):
        with RelevantCausalRecorder(self.path, retention_hours=12) as recorder:
            self._record_light_off_plus_brightness(recorder)
            raw_latest = recorder.for_entity("light.salle_de_bain")[0]
            self.assertEqual(raw_latest.attribute, "brightness")

            selected = recorder.find_best("light.salle_de_bain")
            self.assertIsNone(selected.attribute)
            self.assertEqual(selected.event_kind, "turned_off")
            self.assertEqual(selected.after_value, "off")
            self.assertEqual(selected.reason, "il n'y avait plus de mouvement")

    def test_same_time_generic_lookup_also_prefers_primary_state(self):
        with RelevantCausalRecorder(self.path, retention_hours=12) as recorder:
            self._record_light_off_plus_brightness(recorder)
            selected = recorder.find_best(
                "light.salle_de_bain",
                observed_time=self.now.isoformat(),
            )
            self.assertIsNone(selected.attribute)
            self.assertEqual(selected.after_value, "off")

    def test_explicit_attribute_still_selects_attribute_row(self):
        with RelevantCausalRecorder(self.path, retention_hours=12) as recorder:
            self._record_light_off_plus_brightness(recorder)
            selected = recorder.find_best(
                "light.salle_de_bain",
                attribute="brightness",
            )
            self.assertEqual(selected.attribute, "brightness")
            self.assertEqual(selected.after_value, 0)

    def test_explicit_value_is_never_ignored(self):
        with RelevantCausalRecorder(self.path, retention_hours=12) as recorder:
            self._record_light_off_plus_brightness(recorder)
            selected = recorder.find_best(
                "light.salle_de_bain",
                observed_value="off",
            )
            self.assertIsNone(selected.attribute)
            self.assertEqual(selected.after_value, "off")
            self.assertIsNone(
                recorder.find_best("light.salle_de_bain", observed_value="unseen")
            )


if __name__ == "__main__":
    unittest.main()
