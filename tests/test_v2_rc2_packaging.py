import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_v2_rc2
from activity_reader_v2 import ActivityTraceReaderV2


class V2RC2PackagingTests(unittest.TestCase):
    def test_historical_candidate_version_and_reader(self):
        self.assertEqual(main_v2_rc2.VERSION, "0.3.0-rc.2")
        self.assertIs(main_v2_rc2.ActivityTraceReaderV2, ActivityTraceReaderV2)

    def test_historical_private_image_workflow_remains_scoped(self):
        workflow = (ROOT / ".github" / "workflows" / "publish-v2-rc2-image.yml").read_text(encoding="utf-8")
        self.assertIn("candidate-v2-rc2", workflow)
        self.assertIn("elise-investigator-v2-rc2-private:0.3.0-rc.2", workflow)
        self.assertIn("platforms: linux/amd64", workflow)

    def test_cover_fix_stays_cover_only_at_boundary(self):
        source = (APP / "activity_reader_v2.py").read_text(encoding="utf-8")
        self.assertIn('entity_id.startswith("cover.")', source)
        self.assertIn('record.origin_type == "unknown"', source)

    def test_dev54_safe_fallback_remains_untouched(self):
        fallback = (APP / "main_dev54.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.0-dev.54"', fallback)


if __name__ == "__main__":
    unittest.main()
