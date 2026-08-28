from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_dev29 as dev29
import main_dev34 as dev34
import main_dev34_1 as dev34_1


class TestDev34StorageIsolation(unittest.TestCase):
    def test_dev34_1_uses_dedicated_memory_database(self):
        old_journal = dev29.JOURNAL_FILE
        old_version = dev34.VERSION
        try:
            dev34_1.configure_storage_isolation()
            self.assertEqual(
                dev29.JOURNAL_FILE,
                Path("/data") / "conscious_memory.sqlite3",
            )
            self.assertNotEqual(
                dev29.JOURNAL_FILE,
                Path("/data") / "causal_journal.sqlite3",
            )
            self.assertEqual(dev34.VERSION, "0.2.0-dev.34.1")
        finally:
            dev29.JOURNAL_FILE = old_journal
            dev34.VERSION = old_version

    def test_historical_journal_path_remains_defined_in_dev29(self):
        self.assertEqual(
            Path("/data") / "causal_journal.sqlite3",
            Path(dev29.DATA_DIR) / "causal_journal.sqlite3",
        )


if __name__ == "__main__":
    unittest.main()
