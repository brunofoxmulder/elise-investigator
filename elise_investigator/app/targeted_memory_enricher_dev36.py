from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from action_effect_cause import select_effect_linked_cause
from branch_decision_cause import select_branch_decision_cause
from causal_recorder import CausalRecord
from causal_utils import walk_contains
from human_cause import select_human_cause
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
        # Logbook state is useful for a primary state transition. Attribute-only
        # changes can share the same state and are selected primarily by context/time.
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
    """Enrich one already-captured memory episode with bounded HA reads.

    This is deliberately not the historical reverse investigator. The caller
    supplies one entity episode. We read only that entity's tiny Logbook window;
    if Home Assistant names one automation/script in the context, we inspect only
    that source's nearest trace and require a runtime command targeting the entity.
    """

    def __init__(self, ha, trace_investigator):
        self.ha = ha
        self.trace_investigator = trace_investigator
        self.logbook_reads = 0
        self.trace_reads = 0

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

    async def _trace_reason(
        self,
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        bundle = await self.trace_investigator._best_trace_for_source(
            source_entity_id, record.normalized_time()
        )
        self.trace_reads += 1
        if not isinstance(bundle, dict):
            return None, None, None
        detail = bundle.get("detail")
        if not isinstance(detail, dict):
            return None, _trace_run_id(bundle), None

        # A nearby trace is not enough. It must contain an executed runtime
        # command that actually targets the entity whose effect we memorized.
        if not executed_trace_actions(detail, record.entity_id):
            return None, _trace_run_id(bundle), None

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
        # time_pattern and other purely technical triggers intentionally remain
        # without a user-facing reason unless the trace exposes a local decision.
        return text, _trace_run_id(bundle), _compact_human_cause(human_cause)

    async def enrich(self, records: list[CausalRecord]) -> bool:
        records = [record for record in records if record.record_id is not None]
        if not records:
            return False
        # Prefer the most recent primary state transition as the causal anchor;
        # otherwise use the latest attribute change from the same episode.
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
            # This proves the service context, not who initiated it. Keep it as
            # internal evidence and do not invent a user/voice/integration source.
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
        if human_cause:
            proof["human_cause"] = human_cause

        changed = False
        for original in records:
            current = self.ha_recorder.get(original.record_id) if hasattr(self, "ha_recorder") else original
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
        # Alias used only to reload rows by id before updating after a debounce.
        self.ha_recorder = recorder
        return self
