"""Run existing behavior contracts through RC12, without altering their fixtures."""
from unittest.mock import patch

import test_causal_resolver_v2 as base_cases
import test_causal_resolver_v2_matrix as matrix_cases
import test_v2_rc11_exact_config_commands as rc11_cases
from activity_reader_rc12 import ActivityTraceReaderRC12
from causal_resolver_rc12 import resolve_cause_rc12


class RC12ExistingCommandSafetyTests(rc11_cases.RC11ExactConfigCommandTests):
    def setUp(self):
        resolver = patch.object(rc11_cases, "resolve_cause_rc11", resolve_cause_rc12)
        reader = patch.object(rc11_cases, "ActivityTraceReaderRC11", ActivityTraceReaderRC12)
        resolver.start()
        reader.start()
        self.addCleanup(resolver.stop)
        self.addCleanup(reader.stop)


class RC12ExistingCauseTests(base_cases.CausalResolverV2Tests):
    def setUp(self):
        resolver = patch.object(base_cases, "resolve_cause", lambda result: resolve_cause_rc12(result, None))
        resolver.start()
        self.addCleanup(resolver.stop)


class RC12ExistingTerrainMatrix(matrix_cases.CausalResolverV2TerrainMatrix):
    def setUp(self):
        resolver = patch.object(matrix_cases, "resolve_cause", lambda result: resolve_cause_rc12(result, None))
        resolver.start()
        self.addCleanup(resolver.stop)
