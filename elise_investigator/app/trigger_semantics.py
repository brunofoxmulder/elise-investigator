from __future__ import annotations

import unicodedata
from typing import Any

from causal_utils import device_class, duration_seconds, duration_text, friendly_name, state_value, trace_detail
from human_cause import human_cause_text as _base_human_cause_text
from human_cause import human_rule_text as _base_human_rule_text
from investigator import _extract_trace_trigger
from models import InvestigationResult
from proof_policy import executed_trace_actions


def complete_confirmed_trace_chain(result: InvestigationResult) -> None:
    """Restore the runtime causal chain for a source confirmed by reverse trace search.

    Reverse search can prove one automation/script by its executed target command without
    populating ``result.chain``. The trace itself is already direct evidence, so this
    function exposes only facts read from that executed trace: its runtime trigger, the
    confirmed source and runtime commands targeting the investigated entity.

    Configuration is never used as proof here.
    """
    if result.status != "confirmed":
        return
    source_kind = str(result.cause.get("type") or "")
    source_entity = str(result.cause.get("entity_id") or "")
    if source_kind not in {"automation", "script"} or not source_entity:
        return
    if result.cause.get("system_confirmed") is not True:
        return
    if any(step.get("kind") == source_kind and step.get("proven") is True for step in result.chain):
        return

    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return

    runtime_actions = executed_trace_actions(detail, result.entity_id)
    if not runtime_actions:
        return

    trigger = _extract_trace_trigger(detail)
    if trigger and not any(
        step.get("kind") == "trigger" and step.get("proven") is True for step in result.chain
    ):
        result.chain.append({"kind": "trigger", "detail": trigger, "proven": True})

    result.chain.append({"kind": source_kind, "entity_id": source_entity, "proven": True})
    for action in runtime_actions:
        result.chain.append({"kind": "command", **action, "proven": True})


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").casefold()


def _sun_text(detail: dict[str, Any]) -> str | None:
    event = str(detail.get("event") or "").lower()
    if event not in {"sunset", "sunrise"}:
        return None

    offset_seconds = duration_seconds(detail.get("offset"))
    if event == "sunset":
        event_text = "le soleil s'est couché"
        future_text = "le coucher du soleil"
    else:
        event_text = "le soleil s'est levé"
        future_text = "le lever du soleil"

    if offset_seconds is None or abs(offset_seconds) < 0.5:
        return event_text
    duration = duration_text(abs(offset_seconds))
    if not duration:
        return event_text
    if offset_seconds > 0:
        return f"{event_text} il y a {duration}"
    return f"il restait {duration} avant {future_text}"


def _device_state_text(cause: dict[str, Any], detail: dict[str, Any]) -> str | None:
    after = state_value(detail.get("to_state"))
    if after is None:
        after = detail.get("to")
    after_text = str(after).lower()
    label = friendly_name(cause)
    label_norm = _norm(label)
    klass = _norm(device_class(cause))

    # Prefer the semantic name Home Assistant exposes for the entity when its generic
    # device class is broader (for example a window contact reported as class "door").
    if "fenetre" in label_norm or klass == "window":
        if after_text == "on":
            return "la fenêtre a été ouverte"
        if after_text == "off":
            return "la fenêtre a été refermée"
    if "porte" in label_norm or klass == "door":
        if after_text == "on":
            return "la porte a été ouverte"
        if after_text == "off":
            return "la porte a été refermée"

    trigger_type = str(detail.get("type") or "").lower()
    if trigger_type == "opened":
        return f"« {label} » a été ouvert"
    if trigger_type in {"closed", "not_opened"}:
        return f"« {label} » a été fermé"
    if after is not None:
        return f"« {label} » est passé à {after}"
    return None


def human_cause_text(cause: dict[str, Any]) -> str | None:
    """Render generic Home Assistant trigger semantics without device-specific rules."""
    detail = cause.get("detail")
    if not isinstance(detail, dict):
        return None
    platform = str(detail.get("platform") or detail.get("trigger") or "").lower()

    if platform == "sun":
        text = _sun_text(detail)
        if text:
            return text
    if platform == "device":
        text = _device_state_text(cause, detail)
        if text:
            return text
    return _base_human_cause_text(cause)


def human_rule_text(cause: dict[str, Any], result: InvestigationResult) -> str | None:
    detail = cause.get("detail")
    if isinstance(detail, dict):
        platform = str(detail.get("platform") or detail.get("trigger") or "").lower()
        if platform == "sun":
            event = str(detail.get("event") or "").lower()
            offset_seconds = duration_seconds(detail.get("offset"))
            duration = duration_text(abs(offset_seconds or 0))
            domain = result.entity_id.split(".", 1)[0]
            if duration and domain == "cover":
                if event == "sunset" and (offset_seconds or 0) > 0:
                    return f"La règle prévoit la fermeture {duration} après le coucher du soleil"
                if event == "sunrise" and (offset_seconds or 0) < 0:
                    return f"La règle prévoit l'action {duration} avant le lever du soleil"
    return _base_human_rule_text(cause, result)
