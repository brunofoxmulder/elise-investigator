from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from targeted_memory_enricher_v2 import _select_unique_trace_match


def _match(runtime_distance, summary_distance, run_id):
    return (runtime_distance, summary_distance, {"run_id": run_id}, run_id)


class TargetedMemoryEnricherV2SelectionTests(unittest.TestCase):
    def test_unique_runtime_distance_wins(self):
        selected = _select_unique_trace_match(
            [
                _match(4.0, 15.0, "older"),
                _match(1.0, 20.0, "best"),
            ]
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected[3], "best")

    def test_runtime_tie_uses_unique_trace_start_distance(self):
        selected = _select_unique_trace_match(
            [
                _match(1.0, 18.0, "older"),
                _match(1.0, 3.0, "best"),
            ]
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected[3], "best")

    def test_no_command_timestamps_uses_unique_nearest_exact_trace_start(self):
        selected = _select_unique_trace_match(
            [
                _match(None, 40.0, "older"),
                _match(None, 2.0, "best"),
            ]
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected[3], "best")

    def test_exact_timing_tie_still_fails_closed(self):
        selected = _select_unique_trace_match(
            [
                _match(1.0, 3.0, "a"),
                _match(1.0, 3.0, "b"),
            ]
        )
        self.assertIsNone(selected)

    def test_exact_untimed_start_tie_still_fails_closed(self):
        selected = _select_unique_trace_match(
            [
                _match(None, 3.0, "a"),
                _match(None, 3.0, "b"),
            ]
        )
        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
