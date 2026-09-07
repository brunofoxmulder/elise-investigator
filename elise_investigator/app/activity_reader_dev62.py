from __future__ import annotations

from activity_reader_dev61 import ActivityTraceReader as Dev61ActivityTraceReader
from targeted_memory_enricher_dev62 import TargetedMemoryEnricher as Dev62TargetedTraceHelper


class ActivityTraceReader(Dev61ActivityTraceReader):
    """dev.62 keeps dev.61 Logbook chaining and swaps only trace semantics."""

    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.trace_helper = (
            Dev62TargetedTraceHelper(ha, trace_investigator)
            if trace_investigator is not None
            else None
        )
