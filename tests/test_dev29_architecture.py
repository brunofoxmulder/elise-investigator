import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


class TestDev29Architecture(unittest.TestCase):
    def test_candidate_launcher_uses_current_wrapper(self):
        run_sh = (ROOT / "elise_investigator" / "run.sh").read_text(encoding="utf-8")
        supported = (
            "main_dev55.py", "main_dev56.py", "main_dev57.py", "main_dev58.py",
            "main_dev59.py", "main_dev60.py", "main_dev61.py", "main_dev62.py",
            "main_dev63.py", "main_dev64.py", "main_dev65.py", "main_dev66.py",
            "main_dev67.py", "main_dev68.py", "main_dev69.py", "main_dev70.py",
            "main_dev71.py", "main_dev72.py", "main_dev73.py", "main_v2_rc1.py",
            "main_v2_rc2.py", "main_v2_rc3.py", "main_v2_rc4.py", "main_v2_rc5.py",
        )
        self.assertTrue(any(name in run_sh for name in supported))
        self.assertNotIn("main_dev54.py", run_sh)
        self.assertNotIn("main_mcp_inprocess.py", run_sh)

    def test_manual_investigate_endpoint_is_not_replaced_in_dev29_base(self):
        source = (APP / "main_dev29.py").read_text(encoding="utf-8")
        self.assertIn("base.ask = recorder_first_ask", source)
        self.assertNotIn("base.investigate =", source)
        self.assertIn("manual /investigate endpoint remains untouched", source)

    def test_journal_uses_separate_dev16_engine_without_replacing_manual_engine_in_dev29(self):
        source = (APP / "main_dev29.py").read_text(encoding="utf-8")
        self.assertIn("V02Investigator", source)
        self.assertIn('app["causal_investigator"]', source)
        self.assertIn('app["investigator"]', source)
        self.assertNotIn('app["investigator"] = causal_investigator', source)
