import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_v2_rc9
from activity_reader_rc9 import ActivityTraceReaderRC9


class V2RC9PackagingTests(unittest.TestCase):
    def test_candidate_version_and_reader(self):
        self.assertEqual(main_v2_rc9.VERSION, "0.3.0-rc.9")
        self.assertIs(main_v2_rc9.ActivityTraceReaderRC9, ActivityTraceReaderRC9)

    def test_generic_launcher_points_to_v2_rc9(self):
        run = (ROOT / "elise_investigator" / "run.sh").read_text(encoding="utf-8")
        self.assertIn("exec python3 main_v2_rc9.py", run)

    def test_manifest_version_matches_candidate(self):
        config = (ROOT / "elise_investigator" / "config.yaml").read_text(encoding="utf-8")
        self.assertIn('version: "0.3.0-rc.9"', config)

    def test_private_image_workflow_is_rc9_scoped(self):
        workflow = (ROOT / ".github" / "workflows" / "publish-v2-rc5-image.yml").read_text(encoding="utf-8")
        self.assertIn("candidate-v2-rc9", workflow)
        self.assertIn("elise-investigator-v2-rc9-private:0.3.0-rc.9", workflow)
        self.assertIn("platforms: linux/amd64", workflow)

    def test_v2_resolver_remains_unchanged(self):
        source = (APP / "causal_resolver_rc9.py").read_text(encoding="utf-8")
        self.assertIn("resolve_cause_v2(result)", source)
        resolver = (APP / "causal_resolver_v2.py").read_text(encoding="utf-8")
        self.assertNotIn("rc.9", resolver)

    def test_dev54_safe_fallback_remains_untouched(self):
        fallback = (APP / "main_dev54.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.0-dev.54"', fallback)


if __name__ == "__main__":
    unittest.main()
