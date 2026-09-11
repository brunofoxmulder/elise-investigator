from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_arch_v2
from activity_reader_v2 import ActivityTraceReaderV2


class MainArchV2Tests(unittest.TestCase):
    def test_wrapper_points_to_clean_v2_reader(self):
        self.assertEqual(main_arch_v2.VERSION, "0.2.0-arch-v2")
        self.assertIs(main_arch_v2.ActivityTraceReaderV2, ActivityTraceReaderV2)

    def test_architecture_wrapper_is_not_promoted_to_addon_runtime(self):
        run_sh = (ROOT / "elise_investigator" / "run.sh").read_text(encoding="utf-8")
        config = (ROOT / "elise_investigator" / "config.yaml").read_text(encoding="utf-8")
        self.assertNotIn("main_arch_v2.py", run_sh)
        self.assertNotIn("0.2.0-arch-v2", config)

    def test_dev54_safe_fallback_is_untouched(self):
        stable = (APP / "main_dev54.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.0-dev.54"', stable)


if __name__ == "__main__":
    unittest.main()
