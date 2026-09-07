from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev36 import TargetedMemoryEnricher as TargetedTraceHelper

_TECHNICAL_STATES = {"unknown", "unavailable"}


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _origin(entry: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """Respect Activity attribution: automation/script wins over inherited user context."""
    source = str(entry.get("context_entity_id") or "").strip()
    name = str(entry.get("context_entity_id_name") or "").strip() or None
    if source.startswith("automation."):
        return "automation", source, name
    if source.startswith("script."):
        return "script", source, name
    if entry.get("context_user_id"):
        return "user", None, None
    return "unknown", None, None


def _native_message(entry: dict[str, Any]) -> str | None:
    text = str(entry.get("context_message") or "").strip()
    return text or None


def _native_source(entry: dict[str, Any]) -> str | None:
    text = str(entry.get("context_source") or "").strip()
    return text or None


def _usable(entry: dict[str, Any], entity_id: str) -> bool:
    if str(entry.get("entity_id") or "") != entity_id:
        return False
    state = entry.get("state")
    if state is None:
        return False
    return str(state).casefold() not in _TECHNICAL_STATES


def select_activity_entry(entries: list[dict[str, Any]], entity_id: str) -> dict[str, Any] | None:
    """Return the latest real Activity state row.

    dev.60 deliberately does not replace the fact being explained with an older,
    better-attributed row. Activity is authoritative and only technical
    unknown/unavailable noise is ignored.
    """
    usable = [entry for entry in entries if isinstance(entry, dict) and _usable(entry, entity_id)]
    usable.sort(
        key=lambda entry: _dt(entry.get("when")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return usable[0] if usable else None


def _context_ids(entry: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("context_id", "context_parent_id"):
        value = entry.get(key)
        if value:
            ids.add(str(value))
    context = entry.get("context")
    if isinstance(context, dict):
        for key in ("id", "parent_id"):
            value = context.get(key)
            if value:
                ids.add(str(value))
    return ids


def _attribution_entry(
    fact: dict[str, Any], entries: list[dict[str, Any]], entity_id: str
) -> dict[str, Any]:
    """Use another Activity row only when HA exposes an explicit context link.

    The returned row may carry attribution, but the functional fact/time/state
    always remain those of *fact*. There is no time-window correlation.
    """
    fact_origin, _, _ = _origin(fact)
    if fact_origin != "unknown" or _native_message(fact) or _native_source(fact):
        return fact

    fact_ids = _context_ids(fact)
    if not fact_ids:
        return fact

    candidates = [entry for entry in entries if isinstance(entry, dict) and _usable(entry, entity_id)]
    candidates.sort(
        key=lambda entry: _dt(entry.get("when")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    for entry in candidates:
        if entry is fact:
            continue
        if not (fact_ids & _context_ids(entry)):
            continue
        origin, _, _ = _origin(entry)
        if origin != "unknown" or _native_message(entry) or _native_source(entry):
            return entry
    return fact


def _event_kind(state: Any) -> str:
    value = str(state or "").casefold()
    return {
        "on": "turned_on",
        "off": "turned_off",
        "open": "opened",
        "closed": "closed",
        "opening": "opening",
        "closing": "closing",
        "locked": "locked",
        "unlocked": "unlocked",
    }.get(value, "state_changed")


class ActivityFirstReader:
    """Thin read-only adapter over Home Assistant Activity/Logbook."""

    def __init__(self, ha, trace_investigator=None):
        self.ha = ha
        self.trace_helper = TargetedTraceHelper(ha, trace_investigator) if trace_investigator else None

    def set_mcp_client(self, client) -> None:
        if self.trace_helper is not None:
            self.trace_helper.set_mcp_client(client)

    async def investigate(self, entity_id: str, *, hours: int = 12) -> CausalRecord | None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=max(1, min(int(hours), 72)))
        entries = await self.ha.get_logbook(entity_id, start, end)
        fact = select_activity_entry(entries, entity_id)
        if fact is None:
            return None

        attribution = _attribution_entry(fact, entries, entity_id)
        origin_type, source_entity_id, source_name = _origin(attribution)
        message = _native_message(attribution)
        source_hint = _native_source(attribution)
        when = _dt(fact.get("when")) or end

        # A native context_message is treated as Activity's explicit explanation.
        # context_source is kept as a useful trigger hint, but for automations/scripts
        # it is not promoted to the final reason until the exact execution trace has
        # had a chance to explain the specific action.
        reason = message
        reason_code = "ha_2026_9_activity_native" if reason else None
        record = CausalRecord(
            entity_id=entity_id,
            event_time=when.isoformat(),
            event_kind=_event_kind(fact.get("state")),
            after_value=fact.get("state"),
            origin_type=origin_type,
            source_entity_id=source_entity_id,
            source_name=source_name,
            reason=reason,
            reason_code=reason_code,
            trigger={
                "ha_activity_fact": dict(fact),
                "ha_activity_attribution": dict(attribution),
                "ha_activity_source_hint": source_hint,
            },
            confidence="confirmed",
        )

        if origin_type in {"automation", "script"} and not message and self.trace_helper is not None:
            trace_reason, run_id, human_cause = await self.trace_helper._trace_reason(
                record, source_entity_id, source_name, origin_type
            )
            if trace_reason:
                record.reason = trace_reason
                record.reason_code = "ha_activity+targeted_trace_detail"
                record.trace_run_id = run_id
                if human_cause:
                    record.trigger["human_cause"] = human_cause

        # If the exact trace cannot add detail, preserve HA Activity's native source
        # hint instead of inventing a cause. This keeps good native cases such as a
        # simple numeric-state automation useful without claiming more than HA knows.
        if not record.reason and source_hint:
            record.reason = source_hint
            record.reason_code = "ha_2026_9_activity_source_hint"

        return record
