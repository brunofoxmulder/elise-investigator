from __future__ import annotations

import re

from activity_reader_dev63 import ActivityTraceReader as Dev63ActivityTraceReader
from activity_reader_dev70 import _functional_entries
from targeted_memory_enricher_v2 import TargetedMemoryEnricherV2

_RAW_PROVIDER_TRIGGER = re.compile(r"^\s*triggered\s+by\b", re.IGNORECASE)


def _raw_provider_reason(value: object) -> bool:
    return isinstance(value, str) and bool(_RAW_PROVIDER_TRIGGER.match(value))


class ActivityTraceReaderV2(Dev63ActivityTraceReader):
    """Activity/Logbook evidence reader with V2 causal semantics.

    The evidence plumbing intentionally stops at dev.63: Activity fact selection,
    explicit HA context linkage and cover movement attribution are reused. The causal
    policy chain dev.68 -> dev.70 -> dev.71 -> dev.72 -> dev.73 is not inherited.

    V2 adds only bounded evidence rules:
    - collapse newer same-functional-state refresh rows when a real boundary is visible;
    - use TargetedMemoryEnricherV2 as the single trace semantic resolver/renderer;
    - disable the legacy one-upstream-hop prose concatenation. Future upstream reasoning
      must return structured evidence to the same resolver instead of mutating `reason`.
    """

    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.trace_helper = (
            TargetedMemoryEnricherV2(ha, trace_investigator)
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
            _functional_entries(entries, entity_id),
            end_time=end_time,
            hours=hours,
            # V2 forbids the legacy post-resolver text mutation performed by dev.61.
            allow_upstream=False,
        )
        if record is None:
            return None

        # Provider prose is evidence only. V2 never exposes Home Assistant's English
        # `triggered by ...` sentence as its human causal explanation.
        if (
            record.origin_type in {"automation", "script"}
            and _raw_provider_reason(record.reason)
        ):
            trigger = record.trigger if isinstance(record.trigger, dict) else {}
            trigger["suppressed_native_reason"] = record.reason
            trigger["suppressed_native_reason_code"] = record.reason_code
            record.trigger = trigger
            record.reason = None
            record.reason_code = None

        return record
