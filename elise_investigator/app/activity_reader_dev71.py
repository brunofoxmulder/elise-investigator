from __future__ import annotations

from activity_reader_dev70 import ActivityTraceReader as Dev70ActivityTraceReader
from targeted_memory_enricher_dev71 import TargetedMemoryEnricher as Dev71TargetedTraceHelper


class ActivityTraceReader(Dev70ActivityTraceReader):
    """dev.71: dev.70 fact selection plus fail-closed automation reason rendering."""

    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.trace_helper = (
            Dev71TargetedTraceHelper(ha, trace_investigator)
            if trace_investigator is not None
            else None
        )

    async def _record_from_entries(
        self,
        entity_id,
        entries,
        *,
        end_time,
        hours: int,
        allow_upstream: bool,
    ):
        record = await super()._record_from_entries(
            entity_id,
            entries,
            end_time=end_time,
            hours=hours,
            allow_upstream=allow_upstream,
        )
        if record is None:
            return None

        # `context_source` is a native HA hint, not a human explanation. In dev.60/63 it
        # could become the final reason verbatim (e.g. "triggered by state of ...").
        # For automation/script causes, keep it as evidence in record.trigger but never
        # expose it as the final causal sentence. If exact trace semantics cannot produce
        # a reason, fail closed instead of leaking provider text or inventing one.
        if (
            record.origin_type in {"automation", "script"}
            and record.reason_code == "ha_2026_9_activity_source_hint"
        ):
            record.reason = None
            record.reason_code = None

        return record
