import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_v2_rc4
from activity_reader_v2 import ActivityTraceReaderV2


class V2RC4PackagingTests(unittest.TestCase):
    def test_historical_candidate_version_and_reader(self):
        self.assertEqual(main_v2_rc4.VERSION, "0.3.0-rc.4")
        self.assertIs(main_v2_rc4.ActivityTraceReaderV2, ActivityTraceReaderV2)

    def test_historical_wrapper_remains_present(self):
        source = (APP / "main_v2_rc4.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.3.0-rc.4"', source)

    def test_historical_private_image_workflow_remains_scoped(self):
        workflow = (ROOT / ".github" / "workflows" / "publish-v2-rc4-image.yml").read_text(encoding="utf-8")
        self.assertIn("candidate-v2-rc4", workflow)
        self.assertIn("elise-investigator-v2-rc4-private:0.3.0-rc.4", workflow)
        self.assertIn("platforms: linux/amd64", workflow)

    def test_cover_runtime_extension_stays_domain_bounded(self):
        source = (APP / "cover_cause_v2.py").read_text(encoding="utf-8")
        self.assertIn('result.entity_id.split(".", 1)[0] != "cover"', source)
        self.assertIn('service") or "") != "set_cover_position"', source)
        self.assertIn("changed_variables", source)

    def test_dev54_safe_fallback_remains_untouched(self):
        fallback = (APP / "main_dev54.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "0.2.0-dev.54"', fallback)


if __name__ == "__main__":
    unittest.main()
