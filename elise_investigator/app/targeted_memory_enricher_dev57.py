from __future__ import annotations

from datetime import timedelta
from typing import Any

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev36 import (
    TargetedMemoryEnricher as TargetedTraceHelper,
    _effect_context,
    _select_logbook_entry,
)


class TargetedMemoryEnricher:
    """Use HA 2026.9 Activity first; deepen only one identified source if needed.

    The functional event is selected upstream (including the dev.55 technical-state
    filter). This class copies Home Assistant's native Activity attribution. Only
    when Activity identifies one automation/script but gives no semantic reason do
    we read that exact source's nearest trace. There is no reverse search.
    """

    def __init__(self, ha, investigator=None):
        self.ha = ha
        self.investigator = investigator
        self.recorder = None
        self.logbook_reads = 0
        self.trace_reads = 0
        self.direct_trace_failures = 0
        self.mcp_client = None
        self._trace_helper = TargetedTraceHelper(ha, investigator) if investigator is not None else None

    def bind_recorder(self, recorder):
        self.recorder = recorder
        return self

    def set_mcp_client(self, client) -> None:
        self.mcp_client = client
        if self._trace_helper is not None:
            self._trace_helper.set_mcp_client(client)

    @staticmethod
    def _native_reason(entry: dict[str, Any]) -> str | None:
        value = entry.get("context_source") or entry.get("context_message")
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _native_origin(entry: dict[str, Any]) -> tuple[str, str | None, str | None]:
        if entry.get("context_user_id"):
            return "user", None, None
        source = str(entry.get("context_entity_id") or "").strip()
        source_name = str(entry.get("context_entity_id_name") or "").strip() or None
        if source.startswith("automation."):
            return "automation", source, source_name
        if source.startswith("script."):
            return "script", source, source_name
        return "unknown", None, None

    async def _targeted_trace_reason(
        self,
        anchor: CausalRecord,
        origin_type: str,
        source_entity_id: str | None,
        source_name: str | None,
    ) -> tuple[str | None, str | None, dict[str, Any] | None, str | None]:
        """Read one already-identified automation/script trace, never search broadly."""
        helper = self._trace_helper
        if helper is None or not source_entity_id or origin_type not in {"automation", "script"}:
            return None, None, None, None
        before_reads = helper.trace_reads
        before_failures = helper.direct_trace_failures
        reason, run_id, human_cause = await helper._trace_reason(
            anchor, source_entity_id, source_name, origin_type
        )
        self.trace_reads += max(0, helper.trace_reads - before_reads)
        self.direct_trace_failures += max(0, helper.direct_trace_failures - before_failures)
        return reason, run_id, human_cause, helper.last_trace_backend

    async def enrich(self, records: list[CausalRecord]) -> bool:
        if self.recorder is None:
            return False
        records = [record for record in records if record.record_id is not None]
        if not records:
            return False

        primaries = [record for record in records if record.attribute is None]
        anchor = max(primaries or records, key=lambda item: item.normalized_time())
        event_time = anchor.normalized_time()
        self.logbook_reads += 1
        entries = await self.ha.get_logbook(
            anchor.entity_id,
            event_time - timedelta(seconds=5),
            event_time + timedelta(seconds=5),
        )
        entry = _select_logbook_entry(entries, anchor)
        if not isinstance(entry, dict):
            return False

        origin_type, source_entity_id, source_name = self._native_origin(entry)
        reason = self._native_reason(entry)
        if origin_type == "unknown":
            return False

        reason_code = "ha_2026_9_activity_native"
        trace_run_id = None
        human_cause = None
        trace_backend = None

        # Activity is sufficient whenever it already gives a reason. The trace is
        # a strict fallback for the exact automation/script named by Activity.
        if not reason and origin_type in {"automation", "script"}:
            reason, trace_run_id, human_cause, trace_backend = await self._targeted_trace_reason(
                anchor, origin_type, source_entity_id, source_name
            )
            if reason:
                reason_code = "ha_activity+targeted_trace_detail"

        proof = dict(anchor.trigger) if isinstance(anchor.trigger, dict) else {}
        proof["effect_context_id"] = _effect_context(anchor)
        proof["ha_activity"] = {
            key: entry.get(key)
            for key in (
                "when", "context_id", "context_event_type", "context_entity_id",
                "context_entity_id_name", "context_source", "context_message",
                "context_domain", "context_service", "context_user_id",
            )
            if entry.get(key) is not None
        }
        if trace_backend:
            proof["trace_backend"] = trace_backend
        if human_cause:
            proof["human_cause"] = human_cause

        changed = False
        for original in records:
            current = self.recorder.get(original.record_id)
            if current is None:
                continue
            current.origin_type = origin_type
            current.source_entity_id = source_entity_id
            current.source_name = source_name
            current.reason = reason
            current.reason_code = reason_code
            current.trigger = proof
            current.trace_run_id = trace_run_id or current.trace_run_id
            current.confidence = "confirmed"
            self.recorder.update(current)
            changed = True
        return changed
