import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "elise_investigator/app"))

import main_v2_rc11
import main_v2_rc12
from activity_reader_rc12 import ActivityTraceReaderRC12

class RC12PackagingTests(unittest.TestCase):
    def test_candidate_reader_version_and_unchanged_answer_formatter(self):
        self.assertEqual(main_v2_rc12.VERSION, "0.3.0-rc.12")
        self.assertIs(main_v2_rc12.ActivityTraceReaderRC12, ActivityTraceReaderRC12)
        self.assertIs(main_v2_rc12._answer_with_event_age, main_v2_rc11._answer_with_event_age)

    def test_generic_launcher_and_manifest_match_rc12(self):
        launcher = (ROOT / "elise_investigator/run.sh").read_text()
        self.assertEqual(launcher, "#!/usr/bin/with-contenv bashio\nset -e\ncd /app\nexec python3 main_v2_rc12.py\n")
        self.assertIn('version: "0.3.0-rc.12"', (ROOT / "elise_investigator/config.yaml").read_text())

    def test_private_candidate_workflow_validates_before_build(self):
        workflow = (ROOT / ".github/workflows/publish-v2-rc12-image.yml").read_text()
        self.assertIn("refs/heads/candidate-v2-rc12", workflow)
        self.assertIn("elise-investigator-v2-rc12-private:0.3.0-rc.12", workflow)
        self.assertIn("platforms: linux/amd64", workflow)
        self.assertLess(workflow.index("unittest discover"), workflow.index("push: true"))


if __name__ == "__main__":
    unittest.main()
