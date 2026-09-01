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
from causal_recorder_dev47 import LatestPrimaryStateRecorder


BASE = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=2)


def iso(seconds: int) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat()


def record(
    entity_id: str,
    when: int,
    *,
    before,
    after,
    attribute: str | None = None,
    event_kind: str = "state_changed",
) -> CausalRecord:
    return CausalRecord(
        entity_id=entity_id,
        entity_name=entity_id,
        event_time=iso(when),
        event_kind=event_kind,
        before_value=before,
        after_value=after,
        attribute=attribute,
        origin_type="automation",
        reason="test cause",
        confidence="confirmed",
    )


class TestDev47LatestPrimaryState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recorder = LatestPrimaryStateRecorder(Path(self.tmp.name) / "memory.sqlite3")

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    def test_generic_light_question_ignores_later_brightness_attribute(self):
        self.recorder.record(
            record(
                "light.salon",
                1,
                before="off",
                after="on",
                event_kind="turned_on",
            )
        )
        self.recorder.record(
            record(
                "light.salon",
                10,
                before=40,
                after=120,
                attribute="brightness",
                event_kind="brightness_changed",
            )
        )

        found = self.recorder.find_best("light.salon")

        self.assertIsNotNone(found)
        self.assertIsNone(found.attribute)
        self.assertEqual(found.before_value, "off")
        self.assertEqual(found.after_value, "on")
        self.assertEqual(found.event_kind, "turned_on")

    def test_generic_light_off_question_finds_latest_real_on_to_off_change(self):
        self.recorder.record(
            record(
                "light.salon",
                1,
                before="off",
                after="on",
                event_kind="turned_on",
            )
        )
        self.recorder.record(
            record(
                "light.salon",
                20,
                before="on",
                after="off",
                event_kind="turned_off",
            )
        )
        self.recorder.record(
            record(
                "light.salon",
                25,
                before=80,
                after=0,
                attribute="brightness",
                event_kind="brightness_changed",
            )
        )

        found = self.recorder.find_best("light.salon")

        self.assertIsNotNone(found)
        self.assertEqual(found.before_value, "on")
        self.assertEqual(found.after_value, "off")
        self.assertEqual(found.event_kind, "turned_off")

    def test_explicit_brightness_request_keeps_attribute_semantics(self):
        self.recorder.record(
            record(
                "light.salon",
                1,
                before="off",
                after="on",
                event_kind="turned_on",
            )
        )
        self.recorder.record(
            record(
                "light.salon",
                10,
                before=40,
                after=120,
                attribute="brightness",
                event_kind="brightness_changed",
            )
        )

        found = self.recorder.find_best("light.salon", attribute="brightness")

        self.assertIsNotNone(found)
        self.assertEqual(found.attribute, "brightness")
        self.assertEqual(found.after_value, 120)

    def test_explicit_time_keeps_historical_nearest_event_semantics(self):
        self.recorder.record(
            record(
                "light.salon",
                1,
                before="off",
                after="on",
                event_kind="turned_on",
            )
        )
        brightness = self.recorder.record(
            record(
                "light.salon",
                10,
                before=40,
                after=120,
                attribute="brightness",
                event_kind="brightness_changed",
            )
        )

        found = self.recorder.find_best("light.salon", observed_time=brightness.event_time)

        self.assertIsNotNone(found)
        self.assertEqual(found.attribute, "brightness")

    def test_cover_generic_selection_is_identical_to_dev46_recorder(self):
        old = RelevantCausalRecorder(Path(self.tmp.name) / "old.sqlite3")
        try:
            rows = (
                record(
                    "cover.volet_salon_2",
                    1,
                    before="open",
                    after="closing",
                    event_kind="closing",
                ),
                record(
                    "cover.volet_salon_2",
                    10,
                    before=80,
                    after=20,
                    attribute="current_position",
                    event_kind="positioned",
                ),
            )
            for item in rows:
                old.record(item)
                self.recorder.record(
                    CausalRecord(**{key: value for key, value in item.to_dict().items() if key != "record_id"})
                )

            expected = old.find_best("cover.volet_salon_2")
            actual = self.recorder.find_best("cover.volet_salon_2")

            self.assertIsNotNone(expected)
            self.assertIsNotNone(actual)
            self.assertEqual(actual.attribute, expected.attribute)
            self.assertEqual(actual.event_time, expected.event_time)
            self.assertEqual(actual.before_value, expected.before_value)
            self.assertEqual(actual.after_value, expected.after_value)
        finally:
            old.close()

    def test_attribute_only_entity_still_returns_latest_record(self):
        self.recorder.record(
            record(
                "media_player.tv",
                5,
                before=0.2,
                after=0.3,
                attribute="volume_level",
                event_kind="volume_changed",
            )
        )

        found = self.recorder.find_best("media_player.tv")

        self.assertIsNotNone(found)
        self.assertEqual(found.attribute, "volume_level")
        self.assertEqual(found.after_value, 0.3)


if __name__ == "__main__":
    unittest.main()
