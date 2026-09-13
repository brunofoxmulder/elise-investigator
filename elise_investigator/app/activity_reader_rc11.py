from __future__ import annotations

from activity_reader_v2 import ActivityTraceReaderV2
from targeted_memory_enricher_rc11 import TargetedMemoryEnricherRC11


class ActivityTraceReaderRC11(ActivityTraceReaderV2):
    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.trace_helper = (
            TargetedMemoryEnricherRC11(ha, trace_investigator)
            if trace_investigator is not None
            else None
        )

