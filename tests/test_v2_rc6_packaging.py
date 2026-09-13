import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_v2_rc6
from activity_reader_v2 import ActivityTraceReaderV2


class V2RC6PackagingTests(unittest.TestCase):
    def test_historical_candidate_version_and_reader(self):
        self.assertEqual(main_v2_rc6.VERSION, "0.3.0-rc.6")
        self.assertIs(main_v2_rc6.ActivityTraceReaderV2, ActivityTraceReaderV2)

    def test_rc6_wrapper_keeps_common_event_age_renderer(self):
        source = (APP / "main_v2_rc6.py").read_text(encoding="utf-8")
        self.assertIn("answer_from_record", source)
        self.assertIn("ActivityTraceReaderV2", source)

    def test_dev54_safe_fallback_remains_untouched(self):
        fallback = (APP / "main_dev54.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.0-dev.54"', fallback)


if __name__ == "__main__":
    unittest.main()
