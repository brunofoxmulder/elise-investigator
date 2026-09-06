from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev36 import TargetedMemoryEnricher as TargetedTraceHelper

_TECHNICAL_STATES = {"unknown", "unavailable"}
_EPISODE_SECONDS = 60.0


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
    if entry.get("context_user_id"):
        return "user", None, None
    source = str(entry.get("context_entity_id") or "").strip()
    name = str(entry.get("context_entity_id_name") or "").strip() or None
    if source.startswith("automation."):
        return "automation", source, name
    if source.startswith("script."):
        return "script", source, name
    return "unknown", None, None


def _native_reason(entry: dict[str, Any]) -> str | None:
    value = entry.get("context_source") or entry.get("context_message")
    text = str(value or "").strip()
    return text or None


def _usable(entry: dict[str, Any], entity_id: str) -> bool:
    if str(entry.get("entity_id") or "") != entity_id:
        return False
    state = entry.get("state")
    if state is None:
        return False
    return str(state).casefold() not in _TECHNICAL_STATES


def select_activity_entry(entries: list[dict[str, Any]], entity_id: str) -> dict[str, Any] | None:
    """Pick the latest useful HA Activity event without reconstructing causality.

    Activity itself is the source of truth. We ignore only technical availability
    noise. If the latest visible state is merely the terminal step of the same
    short Activity episode and carries no native attribution, use the immediately
    preceding attributed Activity row from that same episode.
    """
    usable = [entry for entry in entries if isinstance(entry, dict) and _usable(entry, entity_id)]
    usable.sort(key=lambda entry: _dt(entry.get("when")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    if not usable:
        return None

    latest = usable[0]
    latest_origin, _, _ = _origin(latest)
    if latest_origin != "unknown" or _native_reason(latest):
        return latest

    latest_time = _dt(latest.get("when"))
    if latest_time is None:
        return latest
    for older in usable[1:]:
        older_time = _dt(older.get("when"))
        if older_time is None:
            continue
        if (latest_time - older_time).total_seconds() > _EPISODE_SECONDS:
            break
        older_origin, _, _ = _origin(older)
        if older_origin != "unknown" or _native_reason(older):
            return older
    return latest


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
        entry = select_activity_entry(entries, entity_id)
        if entry is None:
            return None

        origin_type, source_entity_id, source_name = _origin(entry)
        reason = _native_reason(entry)
        when = _dt(entry.get("when")) or end
        record = CausalRecord(
            entity_id=entity_id,
            event_time=when.isoformat(),
            event_kind=_event_kind(entry.get("state")),
            after_value=entry.get("state"),
            origin_type=origin_type,
            source_entity_id=source_entity_id,
            source_name=source_name,
            reason=reason,
            reason_code="ha_2026_9_activity_native",
            trigger={"ha_activity": dict(entry)},
            confidence="confirmed",
        )

        if not reason and origin_type in {"automation", "script"} and self.trace_helper is not None:
            reason, run_id, human_cause = await self.trace_helper._trace_reason(
                record, source_entity_id, source_name, origin_type
            )
            if reason:
                record.reason = reason
                record.reason_code = "ha_activity+targeted_trace_detail"
                record.trace_run_id = run_id
                if human_cause:
                    record.trigger["human_cause"] = human_cause
        return record
