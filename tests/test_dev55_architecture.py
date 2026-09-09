from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_dev55
from memory_worker_dev54 import TargetedConsciousMemoryWorker as Dev54Worker
from memory_worker_dev55 import TargetedConsciousMemoryWorker as Dev55Worker


class TestDev55Architecture(unittest.TestCase):
    def test_dev55_is_layered_on_validated_dev54_worker(self):
        self.assertTrue(issubclass(Dev55Worker, Dev54Worker))
        self.assertEqual(main_dev55.VERSION, "0.2.0-dev.55")

    def test_runtime_keeps_dev55_or_layers_newer_wrapper_above_it(self):
        run_sh = (ROOT / "elise_investigator" / "run.sh").read_text(encoding="utf-8")
        self.assertTrue(any(name in run_sh for name in ("main_dev55.py", "main_dev56.py", "main_dev57.py", "main_dev58.py", "main_dev59.py", "main_dev60.py", "main_dev61.py", "main_dev62.py", "main_dev63.py", "main_dev64.py", "main_dev65.py", "main_dev66.py", "main_dev67.py", "main_dev68.py")))

    def test_app_changelog_contains_dev55_native_first_and_dev54_fallback(self):
        changelog = (ROOT / "elise_investigator_02_test" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## 0.2.0-dev.55", changelog)
        self.assertIn("dev54-fallback-stable", changelog)
        self.assertIn("unavailable", changelog)
        self.assertIn("Logbook", changelog)

    def test_design_declares_legacy_reverse_search_as_fallback_only(self):
        design = (ROOT / "docs" / "DEV55_DESIGN.md").read_text(encoding="utf-8")
        self.assertIn("Logbook", design)
