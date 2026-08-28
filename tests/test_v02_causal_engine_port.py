import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from v02_investigator import _trace_distance_from_event, normalize_detail_mode


class TestV02CausalEnginePort(unittest.TestCase):
    def test_event_inside_long_trace_matches_execution_interval(self):
        trace = {
            "timestamp": {
                "start": "2026-08-28T10:00:00+00:00",
                "finish": "2026-08-28T10:10:00+00:00",
            }
        }
        event = datetime(2026, 8, 28, 10, 8, tzinfo=timezone.utc)
        self.assertEqual(_trace_distance_from_event(trace, event), 0.0)

    def test_event_after_trace_uses_distance_from_finish_not_start(self):
        trace = {
            "timestamp": {
                "start": "2026-08-28T10:00:00+00:00",
                "finish": "2026-08-28T10:10:00+00:00",
            }
        }
        event = datetime(2026, 8, 28, 10, 12, tzinfo=timezone.utc)
        self.assertEqual(_trace_distance_from_event(trace, event), 120.0)

    def test_detail_mode_fails_back_to_simple(self):
        self.assertEqual(normalize_detail_mode("detailed"), "detailed")
        self.assertEqual(normalize_detail_mode("anything"), "simple")


if __name__ == "__main__":
    unittest.main()
