import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev52 as dev52
from memory_worker_dev46 import TargetedConsciousMemoryWorker


class TestDev52CleanRebuild(unittest.TestCase):
    def test_uses_fresh_storage_files_not_legacy_memory(self):
        dev52.configure_dev52()
        self.assertEqual(
            dev29.JOURNAL_FILE,
            Path("/data") / "conscious_memory_dev52.sqlite3",
        )
        self.assertEqual(
            dev34.REQUEST_JOURNAL_FILE,
            Path("/data") / "investigator_requests_dev52.sqlite3",
        )
        self.assertNotEqual(dev29.JOURNAL_FILE.name, "conscious_memory.sqlite3")

    def test_keeps_exact_dev46_worker(self):
        dev52.configure_dev52()
        self.assertIs(dev34.ConsciousMemoryWorker, TargetedConsciousMemoryWorker)

    def test_reports_dev52_without_changing_engine_version_chain(self):
        dev52.configure_dev52()
        self.assertEqual(dev34.VERSION, "0.2.0-dev.52")


if __name__ == "__main__":
    unittest.main()
