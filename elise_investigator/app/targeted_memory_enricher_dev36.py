from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from action_effect_cause import select_effect_linked_cause
from branch_decision_cause import select_branch_decision_cause
from causal_recorder import CausalRecord
from human_cause import select_human_cause
from mcp_targeted_trace_dev36 import MCPTargetedTraceReader
from models import Evidence, InvestigationResult
from proof_policy import executed_trace_actions
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text


_LOGBOOK_BEFORE_SECONDS = 5.0
_LOGBOOK_AFTER_SECONDS = 5.0
_LOGBOOK_MATCH_SECONDS = 8.0


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


def _entry_time(entry: dict[str, Any]) -> datetime | None:
    return _dt(entry.get("when"))


def _same_value(actual: Any, expected: Any) -> bool:
    if expected is None:
        return True
    if actual is None:
        return False
    if str(actual) == str(expected):
        return True
    try:
        return abs(float(actual) - float(expected)) < 1e-9
    except (TypeError, ValueError):
        return False


def _effect_context(record: CausalRecord) -> str | None:
    proof = record.trigger if isinstance(record.trigger, dict) else {}
    value = proof.get("effect_context_id")
    return str(value) if value else None


def _select_logbook_entry(
    entries: list[dict[str, Any]], record: CausalRecord
) -> dict[str, Any] | None:
    event_time = record.normalized_time()
    target = record.entity_id
    context_id = _effect_context(record)

    candidates: list[tuple[int, float, dict[str, Any]]] = []
    for entry in entries:
        if not isinstance(entry, dict) or str(entry.get("entity_id") or "") != target:
            continue
        when = _entry_time(entry)
        if when is None:
            continue
        distance = abs((when - event_time).total_seconds())
        if distance > _LOGBOOK_MATCH_SECONDS:
            continue
        entry_context = str(entry.get("context_id") or "")
        context_penalty = 0 if context_id and entry_context == context_id else 1
        value_penalty = 0
        if record.attribute is None and entry.get("state") is not None:
            value_penalty = 0 if _same_value(entry.get("state"), record.after_value) else 1
        candidates.append((context_penalty + value_penalty, distance, entry))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _trace_run_id(bundle: dict[str, Any]) -> str | None:
    summary = bundle.get("summary")
    if isinstance(summary, dict):
        for key in ("run_id", "id"):
            if summary.get(key):
                return str(summary[key])
    detail = bundle.get("detail")
    if isinstance(detail, dict):
        for key in ("run_id", "id"):
            if detail.get(key):
                return str(detail[key])
    return None


def _compact_human_cause(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    detail = value.get("detail") if isinstance(value.get("detail"), dict) else None
    out: dict[str, Any] = {
        key: value[key]
        for key in ("kind", "origin", "path", "command_path", "proven")
        if value.get(key) is not None
    }
    if detail:
        out["detail"] = {
            key: detail[key]
            for key in (
                "platform",
                "trigger",
                "entity_id",
                "from",
                "to",
                "for",
                "above",
                "below",
                "event",
                "offset",
                "at",
                "actual",
                "condition_result",
            )
            if detail.get(key) is not None
        }
    return out or None


class TargetedMemoryEnricher:
    """Enrich one already-captured memory episode with bounded read-only reads.

    One tiny Logbook window identifies the context. If it names one automation or
    script, only that source's nearest trace may be read. A trace is accepted only
    when its runtime actions target the memorized entity. No broad reverse search
    is performed and no question ever starts this enrichment.
    """

    def __init__(self, ha, trace_investigator):
        self.ha = ha
        self.trace_investigator = trace_investigator
        self.logbook_reads = 0
        self.trace_reads = 0
        self.direct_trace_failures = 0
        self.mcp_trace_reader: MCPTargetedTraceReader | None = None
        self.last_trace_backend: str | None = None

    def set_mcp_client(self, mcp_client) -> None:
        self.mcp_trace_reader = MCPTargetedTraceReader(mcp_client) if mcp_client else None

    async def _label_cause(self, cause: dict[str, Any] | None) -> None:
        if not isinstance(cause, dict):
            return
        detail = cause.get("detail")
        entity_id = str(detail.get("entity_id") or "") if isinstance(detail, dict) else ""
        if not entity_id:
            return
        try:
            state = await self.ha.get_state(entity_id)
        except Exception:
            return
        if not isinstance(state, dict):
            return
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        if attrs.get("friendly_name"):
            cause["entity_name"] = str(attrs["friendly_name"])
        if attrs.get("device_class"):
            cause["device_class"] = str(attrs["device_class"])
        if attrs.get("unit_of_measurement"):
            cause["unit"] = str(attrs["unit_of_measurement"])

    async def _reason_from_detail(
        self,
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
        detail: dict[str, Any],
        run_id: str | None,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        if not executed_trace_actions(detail, record.entity_id):
            return None, run_id, None

        result = InvestigationResult(
            status="confirmed",
            entity_id=record.entity_id,
            entity_name=record.entity_name,
            event_type=record.event_kind,
            event_time=record.event_time,
            observed={
                "before": record.before_value,
                "after": record.after_value,
                "attribute": record.attribute,
            },
            cause={
                "type": source_kind,
                "entity_id": source_entity_id,
                "name": source_name,
                "system_confirmed": True,
            },
            evidence=[
                Evidence(
                    kind="trace",
                    summary="Trace ciblée de la source indiquée par le Logbook",
                    source=source_entity_id,
                    strength="direct",
                    raw=detail,
                )
            ],
        )
        complete_confirmed_trace_chain(result)
        human_cause = (
            select_effect_linked_cause(result)
            or select_branch_decision_cause(result)
            or select_human_cause(result)
        )
        await self._label_cause(human_cause)
        text = human_cause_text(human_cause) if human_cause else None
        return text, run_id, _compact_human_cause(human_cause)

    async def _trace_reason(
        self,
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        # Prefer the existing direct HA reader because it is one local hop. If
        # Home Assistant refuses the admin-only trace command for the App token,
        # fall back to the already-validated in-process HA-MCP read-only tool.
        bundle: dict[str, Any] | None = None
        try:
            bundle = await self.trace_investigator._best_trace_for_source(
                source_entity_id, record.normalized_time()
            )
            self.trace_reads += 1
        except Exception:
            self.direct_trace_failures += 1

        if isinstance(bundle, dict):
            detail = bundle.get("detail")
            if isinstance(detail, dict):
                self.last_trace_backend = "direct_ha"
                result = await self._reason_from_detail(
                    record,
                    source_entity_id,
                    source_name,
                    source_kind,
                    detail,
                    _trace_run_id(bundle),
                )
                # A trace that exists but does not target the entity is not proof;
                # trying the same source through MCP cannot make it proof.
                if result[2] is not None or result[0] is not None:
                    return result

        reader = self.mcp_trace_reader
        if reader is not None:
            detail = await reader.nearest_detail(
                source_entity_id, record.normalized_time(), record.entity_id
            )
            if isinstance(detail, dict):
                self.last_trace_backend = "ha_mcp"
                return await self._reason_from_detail(
                    record,
                    source_entity_id,
                    source_name,
                    source_kind,
                    detail,
                    str(detail.get("run_id")) if detail.get("run_id") else None,
                )
        return None, _trace_run_id(bundle) if isinstance(bundle, dict) else None, None

    async def enrich(self, records: list[CausalRecord]) -> bool:
        records = [record for record in records if record.record_id is not None]
        if not records:
            return False
        primaries = [record for record in records if record.attribute is None]
        anchor = max(primaries or records, key=lambda item: item.normalized_time())
        event_time = anchor.normalized_time()
        start = event_time - timedelta(seconds=_LOGBOOK_BEFORE_SECONDS)
        end = event_time + timedelta(seconds=_LOGBOOK_AFTER_SECONDS)

        self.logbook_reads += 1
        entries = await self.ha.get_logbook(anchor.entity_id, start, end)
        entry = _select_logbook_entry(entries, anchor)
        if not entry:
            return False

        context_user_id = entry.get("context_user_id")
        context_event_type = str(entry.get("context_event_type") or "")
        source_entity_id = str(entry.get("context_entity_id") or "")
        source_name = str(entry.get("context_entity_id_name") or "") or None

        origin_type = "unknown"
        reason: str | None = None
        reason_code: str | None = None
        trace_run_id: str | None = None
        human_cause: dict[str, Any] | None = None

        if context_user_id:
            origin_type = "user"
            reason_code = "logbook_user_context"
        elif context_event_type == "automation_triggered" and source_entity_id.startswith("automation."):
            origin_type = "automation"
            reason_code = "targeted_logbook_automation_context"
            reason, trace_run_id, human_cause = await self._trace_reason(
                anchor, source_entity_id, source_name, "automation"
            )
        elif context_event_type == "script_started" and source_entity_id.startswith("script."):
            origin_type = "script"
            reason_code = "targeted_logbook_script_context"
            reason, trace_run_id, human_cause = await self._trace_reason(
                anchor, source_entity_id, source_name, "script"
            )
        elif context_event_type == "call_service":
            reason_code = "logbook_call_service_context"

        proof = {
            "effect_context_id": _effect_context(anchor),
            "logbook": {
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
            },
        }
        if self.last_trace_backend:
            proof["trace_backend"] = self.last_trace_backend
        if human_cause:
            proof["human_cause"] = human_cause

        changed = False
        for original in records:
            current = self.recorder.get(original.record_id) if original.record_id is not None else None
            if current is None:
                continue
            current.origin_type = origin_type
            current.source_entity_id = source_entity_id or None
            current.source_name = source_name
            current.reason = reason
            current.reason_code = reason_code
            current.trigger = proof
            current.confidence = "confirmed"
            current.trace_run_id = trace_run_id
            self.recorder.update(current)
            changed = True
        return changed

    def bind_recorder(self, recorder) -> "TargetedMemoryEnricher":
        self.recorder = recorder
        return self
