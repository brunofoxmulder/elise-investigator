from __future__ import annotations

from activity_reader_dev63 import ActivityTraceReader as Dev63ActivityTraceReader
from targeted_memory_enricher_dev68 import TargetedMemoryEnricher as Dev68TargetedTraceHelper


class ActivityTraceReader(Dev63ActivityTraceReader):
    """dev.68 keeps dev.67 Activity selection and changes only exact-trace semantics."""

    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.trace_helper = (
            Dev68TargetedTraceHelper(ha, trace_investigator)
            if trace_investigator is not None
            else None
        )
