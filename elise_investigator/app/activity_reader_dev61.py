from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from activity_reader_dev60 import (
    ActivityFirstReader as Dev60Reader,
    _dt,
    _event_kind,
    _native_message,
    _native_source,
    _origin,
    _usable,
)
from causal_recorder import CausalRecord


_MOVEMENT_TO_TERMINAL = {
    ("opening", "open"),
    ("closing", "closed"),
}


def _sorted_usable(entries: list[dict[str, Any]], entity_id: str) -> list[dict[str, Any]]:
    usable = [entry for entry in entries if isinstance(entry, dict) and _usable(entry, entity_id)]
    usable.sort(
        key=lambda entry: _dt(entry.get("when")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return usable


def _select_fact(entries: list[dict[str, Any]], entity_id: str) -> dict[str, Any] | None:
    usable = _sorted_usable(entries, entity_id)
    return usable[0] if usable else None


def _movement_carrier(
    fact: dict[str, Any], entries: list[dict[str, Any]], entity_id: str
) -> dict[str, Any]:
    """Keep the terminal fact, but borrow attribution from its native movement row.

    This is a state-machine link only: the immediately previous usable row must be
    opening->open or closing->closed for the same cover. No arbitrary time window.
    """
    origin, _, _ = _origin(fact)
    if origin != "unknown" or _native_message(fact) or _native_source(fact):
        return fact
    if not entity_id.startswith("cover."):
        return fact

    usable = _sorted_usable(entries, entity_id)
    try:
        index = usable.index(fact)
    except ValueError:
        return fact
    if index + 1 >= len(usable):
        return fact

    previous = usable[index + 1]
    pair = (str(previous.get("state") or "").casefold(), str(fact.get("state") or "").casefold())
    if pair not in _MOVEMENT_TO_TERMINAL:
        return fact

    previous_origin, _, _ = _origin(previous)
    if previous_origin != "unknown" or _native_message(previous) or _native_source(previous):
        return previous
    return fact


def _human_cause_entity(human_cause: dict[str, Any] | None) -> str | None:
    if not isinstance(human_cause, dict):
        return None
    detail = human_cause.get("detail")
    if not isinstance(detail, dict):
        return None
    entity_id = str(detail.get("entity_id") or "").strip()
    return entity_id or None


def _effect_text(record: CausalRecord) -> str:
    name = record.entity_name or record.entity_id
    domain = record.entity_id.split(".", 1)[0]
    if domain == "cover" and record.event_kind == "closed":
        return f"{name} s'est fermé"
    if domain == "cover" and record.event_kind == "opened":
        return f"{name} s'est ouvert"
    if record.event_kind == "turned_on":
        return f"{name} s'est activé"
    if record.event_kind == "turned_off":
        return f"{name} s'est désactivé"
    return f"{name} est passé à {record.after_value}"


class ActivityTraceReader(Dev60Reader):
    """dev.61: Logbook fact -> exact source trace -> one explicit upstream hop.

    The reader remains bounded and read-only. It never builds a causal graph and
    never searches unrelated entities. An upstream hop is allowed only when the
    exact trace of the identified automation/script explicitly names that entity.
    """

    async def _record_from_entries(
        self,
        entity_id: str,
        entries: list[dict[str, Any]],
        *,
        end_time: datetime,
        hours: int,
        allow_upstream: bool,
    ) -> CausalRecord | None:
        fact = _select_fact(entries, entity_id)
        if fact is None:
            return None

        attribution = _movement_carrier(fact, entries, entity_id)
        origin_type, source_entity_id, source_name = _origin(attribution)
        message = _native_message(attribution)
        source_hint = _native_source(attribution)
        when = _dt(fact.get("when")) or end_time

        record = CausalRecord(
            entity_id=entity_id,
            event_time=when.isoformat(),
            event_kind=_event_kind(fact.get("state")),
            after_value=fact.get("state"),
            origin_type=origin_type,
            source_entity_id=source_entity_id,
            source_name=source_name,
            reason=message,
            reason_code="ha_2026_9_activity_native" if message else None,
            trigger={
                "ha_activity_fact": dict(fact),
                "ha_activity_attribution": dict(attribution),
                "ha_activity_source_hint": source_hint,
            },
            confidence="confirmed",
        )

        human_cause: dict[str, Any] | None = None
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

        if allow_upstream and human_cause:
            upstream_entity = _human_cause_entity(human_cause)
            if upstream_entity and upstream_entity != entity_id:
                upstream = await self._investigate_at(
                    upstream_entity,
                    end_time=when + timedelta(seconds=1),
                    hours=hours,
                    allow_upstream=False,
                )
                if upstream is not None and upstream.origin_type in {"automation", "script"} and upstream.reason:
                    try:
                        state = await self.ha.get_state(upstream.entity_id)
                        attrs = state.get("attributes") if isinstance(state, dict) else None
                        if isinstance(attrs, dict) and attrs.get("friendly_name"):
                            upstream.entity_name = str(attrs["friendly_name"])
                    except Exception:
                        pass
                    record.trigger["upstream"] = upstream.llm_payload()
                    upstream_text = f"{_effect_text(upstream)} parce que {upstream.reason.rstrip('.')}"
                    if record.reason:
                        record.reason = f"{record.reason.rstrip('.')}; {upstream_text}"
                    else:
                        record.reason = upstream_text
                    record.reason_code = "ha_logbook+exact_trace+one_native_hop"

        return record

    async def _investigate_at(
        self,
        entity_id: str,
        *,
        end_time: datetime,
        hours: int,
        allow_upstream: bool,
    ) -> CausalRecord | None:
        bounded_hours = max(1, min(int(hours), 72))
        start = end_time - timedelta(hours=bounded_hours)
        entries = await self.ha.get_logbook(entity_id, start, end_time)
        return await self._record_from_entries(
            entity_id,
            entries,
            end_time=end_time,
            hours=bounded_hours,
            allow_upstream=allow_upstream,
        )

    async def investigate(self, entity_id: str, *, hours: int = 12) -> CausalRecord | None:
        return await self._investigate_at(
            entity_id,
            end_time=datetime.now(timezone.utc),
            hours=hours,
            allow_upstream=True,
        )
