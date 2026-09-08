from __future__ import annotations

from typing import Any

from activity_reader_dev62 import ActivityTraceReader as Dev62ActivityTraceReader
from activity_reader_dev60 import _context_ids, _native_message, _native_source, _origin
from targeted_memory_enricher_dev63 import TargetedMemoryEnricher as Dev63TargetedTraceHelper


def _linked_native_attribution(
    fact: dict[str, Any], current: dict[str, Any], entries: list[dict[str, Any]]
) -> dict[str, Any]:
    """Reuse attribution only through explicit HA context IDs, including non-state rows.

    dev.60/61 searched usable state rows. HA Activity can expose attribution on a linked
    row that is not itself the final state fact. dev.63 therefore scans all Activity rows,
    but still requires an explicit shared context id/parent_id. No time-window matching.
    """
    origin, _, _ = _origin(current)
    if origin != "unknown" or _native_message(current) or _native_source(current):
        return current

    ids = _context_ids(fact) | _context_ids(current)
    if not ids:
        return current

    for entry in entries:
        if not isinstance(entry, dict) or entry is fact or entry is current:
            continue
        if not (ids & _context_ids(entry)):
            continue
        candidate_origin, _, _ = _origin(entry)
        if candidate_origin != "unknown" or _native_message(entry) or _native_source(entry):
            return entry
    return current


class ActivityTraceReader(Dev62ActivityTraceReader):
    """dev.63 keeps Activity-first selection and strengthens explicit native attribution."""

    def __init__(self, ha, trace_investigator=None):
        super().__init__(ha, trace_investigator)
        self.trace_helper = (
            Dev63TargetedTraceHelper(ha, trace_investigator)
            if trace_investigator is not None
            else None
        )

    async def _record_from_entries(
        self,
        entity_id: str,
        entries: list[dict[str, Any]],
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
        if record is None or record.origin_type != "unknown":
            return record

        trigger = record.trigger if isinstance(record.trigger, dict) else {}
        fact = trigger.get("ha_activity_fact")
        current = trigger.get("ha_activity_attribution")
        if not isinstance(fact, dict) or not isinstance(current, dict):
            return record
        attribution = _linked_native_attribution(fact, current, entries)
        if attribution is current:
            return record

        origin_type, source_entity_id, source_name = _origin(attribution)
        if origin_type == "unknown":
            return record
        record.origin_type = origin_type
        record.source_entity_id = source_entity_id
        record.source_name = source_name
        record.trigger["ha_activity_attribution"] = dict(attribution)
        source_hint = _native_source(attribution)
        record.trigger["ha_activity_source_hint"] = source_hint

        message = _native_message(attribution)
        if message:
            record.reason = message
            record.reason_code = "ha_2026_9_activity_native"

        if origin_type in {"automation", "script"} and self.trace_helper is not None:
            trace_reason, run_id, human_cause = await self.trace_helper._trace_reason(
                record, source_entity_id, source_name, origin_type
            )
            if trace_reason:
                record.reason = trace_reason
                record.reason_code = "ha_logbook+exact_trace"
                record.trace_run_id = run_id
                if human_cause:
                    record.trigger["human_cause"] = human_cause

        if not record.reason and source_hint:
            record.reason = source_hint
            record.reason_code = "ha_2026_9_activity_source_hint"
        return record
