"""Replay existing RC12 reader contracts through the persistence-capable reader."""
from unittest.mock import patch

import test_v2_rc12_start_trigger_chain as rc12_cases
import test_v2_rc11_exact_config_commands as rc11_cases
from activity_reader_rc13 import ActivityTraceReaderRC13


class RC13StartTriggerContracts(rc12_cases.RC12StartTriggerTests):
    def setUp(self):
        replacement = patch.object(rc12_cases, "CandidateReader", ActivityTraceReaderRC13)
        replacement.start(); self.addCleanup(replacement.stop)


class RC13CommandSafetyContracts(rc11_cases.RC11ExactConfigCommandTests):
    def setUp(self):
        replacement = patch.object(rc11_cases, "ActivityTraceReaderRC11", ActivityTraceReaderRC13)
        replacement.start(); self.addCleanup(replacement.stop)
