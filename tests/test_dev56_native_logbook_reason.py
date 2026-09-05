from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "elise_investigator" / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import main_dev56
from memory_worker_dev55 import TargetedConsciousMemoryWorker as Dev55Worker
from memory_worker_dev56 import TargetedConsciousMemoryWorker as Dev56Worker
from targeted_memory_enricher_dev45 import TargetedMemoryEnricher as Dev45Enricher
from targeted_memory_enricher_dev56 import TargetedMemoryEnricher as Dev56Enricher, _native_logbook_reason


class TestDev56NativeLogbookReason(unittest.TestCase):
    def test_dev56_layers_on_dev55_worker(self):
        self.assertTrue(issubclass(Dev56Worker, Dev55Worker))
        self.assertEqual(main_dev56.VERSION, "0.2.0-dev.56")

    def test_dev56_keeps_dev45_cover_and_trace_behaviour(self):
        self.assertTrue(issubclass(Dev56Enricher, Dev45Enricher))

    def test_state_source_becomes_conservative_native_reason(self):
        self.assertEqual(
            _native_logbook_reason({"context_source": "state of binary_sensor.rte_tempo_heures_creuses"}),
            "« rte tempo heures creuses » a déclenché l'automatisation",
        )

    def test_numeric_state_source_becomes_conservative_native_reason(self):
        self.assertEqual(
            _native_logbook_reason({"context_source": "numeric state of sensor.sm_s908b_battery_level"}),
            "« sm s908b battery level » a déclenché l'automatisation",
        )

    def test_context_message_is_secondary_native_source(self):
        self.assertEqual(
            _native_logbook_reason({"context_message": "state of binary_sensor.rte_tempo_heures_creuses"}),
            "« rte tempo heures creuses » a déclenché l'automatisation",
        )

    def test_periodic_time_source_is_not_promoted(self):
        self.assertIsNone(_native_logbook_reason({"context_source": "time_pattern every 5 minutes"}))

    def test_missing_source_stays_unknown(self):
        self.assertIsNone(_native_logbook_reason({}))
        self.assertIsNone(_native_logbook_reason(None))


if __name__ == "__main__":
    unittest.main()
