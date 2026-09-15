from __future__ import annotations

from activity_reader_v2 import ActivityTraceReaderV2
from targeted_memory_enricher_rc12 import TargetedMemoryEnricherRC12


class ActivityTraceReaderRC12(ActivityTraceReaderV2):
    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.trace_helper = (
            TargetedMemoryEnricherRC12(ha, trace_investigator)
            if trace_investigator is not None
            else None
        )
