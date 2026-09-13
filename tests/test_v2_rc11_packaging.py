import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_v2_rc11
from activity_reader_rc11 import ActivityTraceReaderRC11


class V2RC11PackagingTests(unittest.TestCase):
    def test_candidate_version_and_reader(self):
        self.assertEqual(main_v2_rc11.VERSION, "0.3.0-rc.11")
        self.assertIs(main_v2_rc11.ActivityTraceReaderRC11, ActivityTraceReaderRC11)

    def test_generic_launcher_and_manifest_point_to_rc11(self):
        run = (ROOT / "elise_investigator" / "run.sh").read_text(encoding="utf-8")
        config = (ROOT / "elise_investigator" / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("exec python3 main_v2_rc11.py", run)
        self.assertIn('version: "0.3.0-rc.11"', config)

    def test_private_image_workflow_is_rc11_scoped(self):
        workflow = (ROOT / ".github" / "workflows" / "publish-v2-rc11-image.yml").read_text(encoding="utf-8")
        self.assertIn("candidate-v2-rc11", workflow)
        self.assertIn("elise-investigator-v2-rc11-private:0.3.0-rc.11", workflow)
        self.assertIn("platforms: linux/amd64", workflow)

    def test_rc9_default_delay_resolver_and_renderer_are_not_modified_by_rc11(self):
        resolver = (APP / "causal_resolver_rc9.py").read_text(encoding="utf-8")
        renderer = (APP / "causal_renderer_rc9.py").read_text(encoding="utf-8")
        self.assertNotIn("rc11", resolver.casefold())
        self.assertNotIn("rc11", renderer.casefold())

    def test_dev54_safe_fallback_remains_untouched(self):
        fallback = (APP / "main_dev54.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.0-dev.54"', fallback)


if __name__ == "__main__":
    unittest.main()

