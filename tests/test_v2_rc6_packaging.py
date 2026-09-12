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
    def test_candidate_version_and_reader(self):
        self.assertEqual(main_v2_rc6.VERSION, "0.3.0-rc.6")
        self.assertIs(main_v2_rc6.ActivityTraceReaderV2, ActivityTraceReaderV2)

    def test_generic_launcher_points_only_to_v2_rc6(self):
        run = (ROOT / "elise_investigator" / "run.sh").read_text(encoding="utf-8")
        self.assertIn("exec python3 main_v2_rc6.py", run)
        self.assertNotIn("exec python3 main_v2_rc5.py", run)

    def test_manifest_version_matches_candidate(self):
        config = (ROOT / "elise_investigator" / "config.yaml").read_text(encoding="utf-8")
        self.assertIn('version: "0.3.0-rc.6"', config)

    def test_private_image_workflow_is_rc6_scoped(self):
        workflow = (ROOT / ".github" / "workflows" / "publish-v2-rc5-image.yml").read_text(encoding="utf-8")
        self.assertIn("candidate-v2-rc6", workflow)
        self.assertIn("elise-investigator-v2-rc6-private:0.3.0-rc.6", workflow)
        self.assertIn("platforms: linux/amd64", workflow)

    def test_rc6_does_not_touch_causal_resolver(self):
        rc6 = (APP / "main_v2_rc6.py").read_text(encoding="utf-8")
        self.assertIn("ActivityTraceReaderV2", rc6)
        resolver = (APP / "causal_resolver_v2.py").read_text(encoding="utf-8")
        self.assertNotIn("event_age", resolver)

    def test_dev54_safe_fallback_remains_untouched(self):
        fallback = (APP / "main_dev54.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.0-dev.54"', fallback)


if __name__ == "__main__":
    unittest.main()
