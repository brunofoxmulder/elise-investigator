import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_v2_rc10
from activity_reader_rc9 import ActivityTraceReaderRC9


class V2RC10PackagingTests(unittest.TestCase):
    def test_historical_candidate_version_and_reader(self):
        self.assertEqual(main_v2_rc10.VERSION, "0.3.0-rc.10")
        self.assertIs(main_v2_rc10.ActivityTraceReaderRC9, ActivityTraceReaderRC9)

    def test_historical_wrapper_remains_available(self):
        wrapper = (APP / "main_v2_rc10.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.3.0-rc.10"', wrapper)

    def test_private_image_workflow_is_rc10_scoped(self):
        workflow = (ROOT / ".github" / "workflows" / "publish-v2-rc5-image.yml").read_text(encoding="utf-8")
        self.assertIn("candidate-v2-rc10", workflow)
        self.assertIn("elise-investigator-v2-rc10-private:0.3.0-rc.10", workflow)
        self.assertIn("platforms: linux/amd64", workflow)

    def test_raw_ha_action_key_fix_is_present(self):
        helper = (APP / "trace_branch_path_dev70.py").read_text(encoding="utf-8")
        self.assertIn('current.get("action")', helper)
        self.assertIn('current.get("actions")', helper)

    def test_dev54_safe_fallback_remains_untouched(self):
        fallback = (APP / "main_dev54.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.0-dev.54"', fallback)


if __name__ == "__main__":
    unittest.main()
