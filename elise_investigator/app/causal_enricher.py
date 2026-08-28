from __future__ import annotations

from typing import Any

from action_effect_cause import select_effect_linked_cause
from branch_decision_cause import select_branch_decision_cause
from causal_events import ObservedChange
from causal_recorder import CausalRecord
from condition_context import extract_passed_conditions
from human_cause import select_human_cause
from models import InvestigationRequest, InvestigationResult
from runtime_decision import extract_runtime_decision
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text


# Deep causal enrichment is intentionally limited to controllable/user-visible
# Home Assistant domains. Sensor telemetry is still recorded by the stream but
# does not trigger expensive reverse automation/trace searches on every update.
ENRICHED_DOMAINS = frozenset(
    {
        "climate",
        "cover",
        "fan",
        "humidifier",
        "input_boolean",
        "light",
        "lock",
        "media_player",
        "switch",
        "vacuum",
        "water_heater",
    }
)

_TRIGGER_KEYS = (
    "platform",
    "entity_id",
    "from",
    "to",
    "for",
    "above",
    "below",
    "event",
    "offset",
    "at",
    "type",
    "actual",
    "condition_result",
)


def initial_record(change: ObservedChange) -> CausalRecord:
    """Persist the observed effect immediately, before any expensive research."""
    direct_user = bool(change.user_id)
    return CausalRecord(
        entity_id=change.entity_id,
        entity_name=change.entity_name,
        event_time=change.event_time,
        event_kind=change.event_kind,
        before_value=change.before_value,
        after_value=change.after_value,
        attribute=change.attribute,
        origin_type="user" if direct_user else "unknown",
        confidence="confirmed" if direct_user else "indeterminate",
        reason_code="context_user_id" if direct_user else None,
    )


def needs_enrichment(change: ObservedChange) -> bool:
    # A direct HA user context is already stronger than a later temporal search.
    return not change.user_id and change.domain in ENRICHED_DOMAINS


def _compact_trigger(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    out: dict[str, Any] = {}
    for key in _TRIGGER_KEYS:
        item = value.get(key)
        if item is not None and isinstance(item, (str, int, float, bool, list, dict)):
            if key == "for" and isinstance(item, dict):
                out[key] = {
                    sub: val
                    for sub, val in item.items()
                    if sub in {"hours", "minutes", "seconds", "milliseconds"}
                    and isinstance(val, (int, float))
                }
            elif not isinstance(item, dict):
                out[key] = item
    for state_key in ("from_state", "to_state"):
        state = value.get(state_key)
        if isinstance(state, dict):
            compact_state: dict[str, Any] = {}
            if state.get("state") is not None:
                compact_state["state"] = state.get("state")
            attrs = state.get("attributes")
            if isinstance(attrs, dict):
                for attr in ("friendly_name", "device_class", "unit_of_measurement"):
                    if attrs.get(attr) is not None:
                        compact_state[attr] = attrs.get(attr)
            if compact_state:
                out[state_key] = compact_state
    return out or None


def _compact_condition(condition: dict[str, Any]) -> dict[str, Any]:
    out = {"role": "condition", "proven": True}
    for key in ("condition_type", "entity_id", "name", "actual", "expected", "above", "below", "unit"):
        if condition.get(key) is not None:
            out[key] = condition[key]
    return out


def _trace_run_id(result: InvestigationResult) -> str | None:
    for evidence in result.evidence:
        if evidence.kind != "trace" or not isinstance(evidence.raw, dict):
            continue
        for key in ("run_id", "id"):
            value = evidence.raw.get(key)
            if value:
                return str(value)
        context = evidence.raw.get("context")
        if isinstance(context, dict) and context.get("id"):
            return str(context["id"])
    return None


def _proven_trigger(result: InvestigationResult) -> dict[str, Any] | None:
    for step in result.chain:
        if step.get("kind") == "trigger" and step.get("proven") is True:
            detail = step.get("detail")
            if isinstance(detail, dict):
                return detail
    return None


def _structured_human_cause(result: InvestigationResult) -> dict[str, Any] | None:
    explanation = result.meta.get("explanation") if isinstance(result.meta, dict) else None
    cause = explanation.get("human_cause") if isinstance(explanation, dict) else None
    return cause if isinstance(cause, dict) and cause.get("proven") is True else None


def _technical_trigger_platform(human_cause: dict[str, Any] | None) -> str:
    detail = human_cause.get("detail") if isinstance(human_cause, dict) else None
    if not isinstance(detail, dict):
        return ""
    return str(detail.get("platform") or detail.get("trigger") or "").lower()


class CausalEnricher:
    """Project a full deterministic investigation into one compact journal row."""

    def __init__(self, investigator, ha):
        self.investigator = investigator
        self.ha = ha

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

    async def enrich(self, change: ObservedChange, record: CausalRecord) -> CausalRecord:
        if not needs_enrichment(change):
            return record

        request = InvestigationRequest(
            entity_id=change.entity_id,
            observed_time=change.event_time,
            observed_value=change.after_value,
            attribute=change.attribute,
            window_minutes=5,
        )
        result = await self.investigator.investigate(request)
        complete_confirmed_trace_chain(result)

        record.confidence = result.status
        cause_type = str(result.cause.get("type") or "unknown")
        system_confirmed = result.cause.get("system_confirmed") is True

        if cause_type == "user" and system_confirmed:
            record.origin_type = "user"
            record.reason_code = "home_assistant_user_context"
            return record

        if cause_type not in {"automation", "script"} or not system_confirmed:
            if cause_type in {"recovery", "integration"} and system_confirmed:
                record.origin_type = "integration"
                record.reason_code = cause_type
            return record

        record.origin_type = cause_type
        record.source_entity_id = result.cause.get("entity_id")
        record.source_name = result.cause.get("name")
        record.trace_run_id = _trace_run_id(result)

        conditions = extract_passed_conditions(result)
        # When the dev.16 enrichment engine already selected a proven action-local
        # cause, reuse that exact selection rather than independently re-ranking it.
        human_cause = _structured_human_cause(result) or (
            select_effect_linked_cause(result)
            or select_branch_decision_cause(result)
            or select_human_cause(result)
        )
        await self._label_cause(human_cause)

        if human_cause:
            text = str(human_cause.get("text") or "").strip() or human_cause_text(human_cause)
            if text:
                record.reason = text
            record.reason_code = str(human_cause.get("origin") or human_cause.get("kind") or "") or None
            record.trace_path = str(human_cause.get("path") or "") or None
            detail = human_cause.get("detail")
            record.trigger = _compact_trigger(detail)
        else:
            record.trigger = _compact_trigger(_proven_trigger(result))
            record.reason_code = "automation_without_functional_reason"

        factors = [_compact_condition(item) for item in conditions]
        if human_cause and human_cause.get("origin") == "choose_default":
            decisive = _compact_trigger(human_cause.get("detail"))
            if decisive:
                factors.insert(0, {"role": "decisive", **decisive})

        # A periodic/time trigger often says only when the automation evaluated,
        # not why it selected the resulting value. For rendered numeric targets,
        # derive the bounded runtime dependency set instead of presenting the timer
        # as the functional reason.
        decision = extract_runtime_decision(result)
        platform = _technical_trigger_platform(human_cause)
        if decision is not None:
            factors = [*decision.factors, *factors]
            if decision.reason and (not record.reason or platform in {"time", "time_pattern"}):
                record.reason = decision.reason
                record.reason_code = "runtime_variable_dependencies"
                record.trace_path = decision.command_path

        record.factors = factors or None
        return record
