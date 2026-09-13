import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_v2_rc7
from activity_reader_v2 import ActivityTraceReaderV2


class V2RC7PackagingTests(unittest.TestCase):
    def test_historical_candidate_version_and_reader(self):
        self.assertEqual(main_v2_rc7.VERSION, "0.3.0-rc.7")
        self.assertIs(main_v2_rc7.ActivityTraceReaderV2, ActivityTraceReaderV2)

    def test_historical_wrapper_remains_present(self):
        source = (APP / "main_v2_rc7.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.3.0-rc.7"', source)
        self.assertIn("ActivityTraceReaderV2", source)
        self.assertIn("answer_from_record", source)

    def test_rc7_keeps_resolver_file_unchanged_by_candidate_wrapper(self):
        resolver = (APP / "causal_resolver_v2.py").read_text(encoding="utf-8")
        self.assertNotIn("rc.7", resolver)

    def test_dev54_safe_fallback_remains_untouched(self):
        fallback = (APP / "main_dev54.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.0-dev.54"', fallback)


if __name__ == "__main__":
    unittest.main()
