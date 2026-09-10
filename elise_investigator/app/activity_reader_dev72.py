from __future__ import annotations

from activity_reader_dev71 import ActivityTraceReader as Dev71ActivityTraceReader
from targeted_memory_enricher_dev72 import TargetedMemoryEnricher as Dev72TargetedTraceHelper


class ActivityTraceReader(Dev71ActivityTraceReader):
    """dev.72: dev.71 fact selection with corrected exact-trace guard semantics."""

    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.trace_helper = (
            Dev72TargetedTraceHelper(ha, trace_investigator)
            if trace_investigator is not None
            else None
        )
