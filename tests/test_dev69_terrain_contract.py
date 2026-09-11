from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_dev68
import main_dev69


class Dev69TerrainContractTests(unittest.TestCase):
    """Freeze the dev.67 terrain lessons without adding another causal engine layer."""

    def test_dev69_is_only_a_qualified_wrapper_over_dev68_logic(self):
        source = (APP / "main_dev69.py").read_text(encoding="utf-8")
        self.assertIn("import main_dev68 as impl", source)
        self.assertIn('VERSION = "0.2.0-dev.69"', source)
        self.assertEqual(main_dev69.VERSION, "0.2.0-dev.69")
        self.assertEqual(main_dev68.VERSION, "0.2.0-dev.68")

    def test_action_local_fix_order_stays_bounded(self):
        source = (APP / "targeted_memory_enricher_dev68.py").read_text(encoding="utf-8")
        expected = [
            "select_effect_linked_cause(result)",
            "select_completed_wait_cause(result)",
            "select_wait_timeout_cause(result)",
            "select_elapsed_delay_cause(result)",
            "select_chosen_branch_conditions(result)",
            "select_trigger_with_true_conditions(result)",
            "select_branch_decision_cause(result)",
            "select_human_cause(result)",
        ]
        positions = [source.index(item) for item in expected]
        self.assertEqual(positions, sorted(positions))

    def test_packaging_remains_the_terrain_proven_dev62_contract(self):
        dockerfile = (ROOT / "elise_investigator" / "Dockerfile").read_text(encoding="utf-8")
        launcher = (ROOT / "elise_investigator" / "run.sh").read_text(encoding="utf-8")
        self.assertIn("COPY run.sh /run.sh", dockerfile)
        self.assertIn("RUN chmod 0755 /run.sh", dockerfile)
        self.assertIn('CMD ["/run.sh"]', dockerfile)
        self.assertIn("#!/usr/bin/with-contenv bashio", launcher)
        supported = (
            "main_dev69.py", "main_dev70.py", "main_dev71.py", "main_dev72.py",
            "main_dev73.py", "main_v2_rc1.py",
        )
        self.assertTrue(any(name in launcher for name in supported))
        self.assertNotIn("run_dev69.sh", launcher)
        self.assertNotIn("run_dev70.sh", launcher)
        self.assertNotIn("run_dev71.sh", launcher)
        self.assertNotIn("run_dev72.sh", launcher)
        self.assertNotIn("run_dev73.sh", launcher)


if __name__ == "__main__":
    unittest.main()
