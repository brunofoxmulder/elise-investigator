from __future__ import annotations

from datetime import timedelta
from typing import Any

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev36 import (
    TargetedMemoryEnricher as Dev36TargetedMemoryEnricher,
    _effect_context,
    _select_logbook_entry,
)


_COVER_EPISODE_MAX_SECONDS = 300.0
_TECHNICAL_REASON_PREFIXES = (
    "state of ",
    "numeric state of ",
    "device of ",
)


def _technical_reason(value: str | None) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return False
    return text.startswith(_TECHNICAL_REASON_PREFIXES) or "binary_sensor." in text


class TargetedMemoryEnricher(Dev36TargetedMemoryEnricher):
    """Dev.37: polish an already valid conscious-memory row.

    The memory capture contract is unchanged. This class only improves causal
    enrichment using facts that are already proven by the event stream or by the
    same cover movement episode. It never performs a broad reverse search.
    """

    def _cover_episode_source(self, anchor: CausalRecord) -> CausalRecord | None:
        if not anchor.entity_id.startswith("cover.") or anchor.attribute is not None:
            return None
        terminal = str(anchor.after_value or "").lower()
        expected_motion = {"closed": "closing", "open": "opening"}.get(terminal)
        if expected_motion is None:
            return None
        # The terminal transition itself must prove that this is the end of the
        # expected movement. This prevents inheritance across unrelated episodes.
        if str(anchor.before_value or "").lower() != expected_motion:
            return None

        older = [
            item
            for item in self.recorder.for_entity(anchor.entity_id, limit=30)
            if item.record_id != anchor.record_id
            and item.attribute is None
            and item.normalized_time() < anchor.normalized_time()
        ]
        if not older:
            return None
        older.sort(key=lambda item: item.normalized_time(), reverse=True)
        start = older[0]
        if str(start.after_value or "").lower() != expected_motion:
            return None
        age = (anchor.normalized_time() - start.normalized_time()).total_seconds()
        if age < 0 or age > _COVER_EPISODE_MAX_SECONDS:
            return None
        if start.origin_type == "user":
            return start
        if start.origin_type in {"automation", "script"} and start.reason and not _technical_reason(start.reason):
            return start
        return None

    def _apply_cover_episode_source(self, records: list[CausalRecord], source: CausalRecord) -> bool:
        changed = False
        for original in records:
            current = self.recorder.get(original.record_id) if original.record_id is not None else None
            if current is None:
                continue
            current.origin_type = source.origin_type
            current.source_entity_id = source.source_entity_id
            current.source_name = source.source_name
            current.reason = source.reason
            current.reason_code = "cover_episode_continuity"
            proof = dict(current.trigger) if isinstance(current.trigger, dict) else {}
            proof["cover_episode"] = {
                "source_record_id": source.record_id,
                "source_event_time": source.event_time,
                "source_after": source.after_value,
                "terminal_event_time": current.event_time,
                "terminal_after": current.after_value,
            }
            current.trigger = proof
            current.confidence = "confirmed"
            current.trace_run_id = source.trace_run_id
            current.trace_path = source.trace_path
            self.recorder.update(current)
            changed = True
        return changed

    async def enrich(self, records: list[CausalRecord]) -> bool:
        records = [record for record in records if record.record_id is not None]
        if not records:
            return False
        primaries = [record for record in records if record.attribute is None]
        anchor = max(primaries or records, key=lambda item: item.normalized_time())

        # A cover's physical terminal state is part of the movement that began
        # earlier. Prefer the already-proven beginning of that exact episode over
        # a fresh interpretation of the terminal state, whose HA context may now
        # belong to a notification or another observer automation.
        cover_source = self._cover_episode_source(anchor)
        if cover_source is not None:
            return self._apply_cover_episode_source(records, cover_source)

        event_time = anchor.normalized_time()
        start = event_time - timedelta(seconds=5)
        end = event_time + timedelta(seconds=5)
        self.logbook_reads += 1
        entries = await self.ha.get_logbook(anchor.entity_id, start, end)
        entry = _select_logbook_entry(entries, anchor)

        captured_origin = anchor.origin_type
        captured_source_entity = anchor.source_entity_id
        captured_source_name = anchor.source_name
        captured_reason = anchor.reason

        origin_type = "unknown"
        source_entity_id: str | None = None
        source_name: str | None = None
        reason: str | None = None
        reason_code: str | None = None
        trace_run_id: str | None = None
        human_cause: dict[str, Any] | None = None

        # Direct user proof always wins and needs no trace.
        if entry and entry.get("context_user_id"):
            origin_type = "user"
            reason_code = "logbook_user_context"
        else:
            context_event_type = str(entry.get("context_event_type") or "") if entry else ""
            logbook_source = str(entry.get("context_entity_id") or "") if entry else ""
            logbook_name = str(entry.get("context_entity_id_name") or "") or None if entry else None

            if context_event_type == "automation_triggered" and logbook_source.startswith("automation."):
                origin_type = "automation"
                source_entity_id = logbook_source
                source_name = logbook_name
                reason_code = "targeted_logbook_automation_context"
            elif context_event_type == "script_started" and logbook_source.startswith("script."):
                origin_type = "script"
                source_entity_id = logbook_source
                source_name = logbook_name
                reason_code = "targeted_logbook_script_context"
            elif captured_origin in {"automation", "script"} and captured_source_entity:
                # The event stream already linked automation_triggered -> command ->
                # effect by HA context. A later Logbook row that only says
                # call_service must not erase that stronger proof.
                origin_type = captured_origin
                source_entity_id = captured_source_entity
                source_name = captured_source_name
                reason_code = "captured_context_preserved"
            elif captured_origin == "user":
                origin_type = "user"
                reason_code = "captured_user_context"
            elif entry and context_event_type == "call_service":
                reason_code = "logbook_call_service_context"

            if origin_type in {"automation", "script"} and source_entity_id:
                reason, trace_run_id, human_cause = await self._trace_reason(
                    anchor, source_entity_id, source_name, origin_type
                )
                if reason:
                    reason_code = f"{reason_code or 'captured_context'}+targeted_trace"
                elif captured_reason and not _technical_reason(captured_reason):
                    reason = captured_reason
                # A raw HA source such as "state of binary_sensor..." remains
                # internal proof; exposing it as the user-facing reason is worse
                # than the explicit no-cause fallback.

        proof = dict(anchor.trigger) if isinstance(anchor.trigger, dict) else {}
        proof["effect_context_id"] = _effect_context(anchor)
        if entry:
            proof["logbook"] = {
                key: entry.get(key)
                for key in (
                    "when",
                    "context_id",
                    "context_event_type",
                    "context_entity_id",
                    "context_entity_id_name",
                    "context_source",
                    "context_domain",
                    "context_service",
                    "context_user_id",
                )
                if entry.get(key) is not None
            }
        if self.last_trace_backend:
            proof["trace_backend"] = self.last_trace_backend
        if human_cause:
            proof["human_cause"] = human_cause

        # If neither Logbook nor the already-captured event context contributes
        # anything, keep the durable raw memory row unchanged.
        if origin_type == "unknown" and entry is None:
            return False

        changed = False
        for original in records:
            current = self.recorder.get(original.record_id) if original.record_id is not None else None
            if current is None:
                continue
            current.origin_type = origin_type
            current.source_entity_id = source_entity_id
            current.source_name = source_name
            current.reason = reason
            current.reason_code = reason_code
            current.trigger = proof
            current.confidence = "confirmed"
            current.trace_run_id = trace_run_id
            self.recorder.update(current)
            changed = True
        return changed
