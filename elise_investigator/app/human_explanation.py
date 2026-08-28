from __future__ import annotations

from typing import Any

from human_cause import human_cause_text, human_rule_text
from models import InvestigationResult


def _format_number(value: Any) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return (f"{number:.3f}").rstrip("0").rstrip(".").replace(".", ",")


def _state_value(state: Any) -> Any:
    return state.get("state") if isinstance(state, dict) else None


def _state_attributes(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    attrs = state.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def _trigger_label(trigger: dict[str, Any]) -> str:
    for key in ("to_state", "from_state"):
        attrs = _state_attributes(trigger.get(key))
        name = attrs.get("friendly_name")
        if name:
            return str(name)
    entity_id = str(trigger.get("entity_id") or "").strip()
    if "." in entity_id:
        entity_id = entity_id.split(".", 1)[1]
    return entity_id.replace("_", " ").strip() or "le déclencheur"


def _trigger_unit(trigger: dict[str, Any]) -> str:
    for key in ("to_state", "from_state"):
        attrs = _state_attributes(trigger.get(key))
        unit = attrs.get("unit_of_measurement")
        if unit:
            return f" {unit}"
    return ""


def _effect_sentence(result: InvestigationResult) -> str | None:
    label = result.entity_name or result.entity_id
    before = result.observed.get("before")
    after = result.observed.get("after")
    attribute = result.observed.get("attribute")

    if attribute in {"current_position", "position"} and after is not None:
        return f"{label} a été positionné à {_format_number(after)} %."

    if result.event_type == "state_change":
        domain = result.entity_id.split(".", 1)[0]
        if domain == "light" and after == "on":
            return f"{label} s'est allumée."
        if domain == "light" and after == "off":
            return f"{label} s'est éteinte."
        if domain == "cover" and after == "closed":
            return f"{label} s'est fermé."
        if domain == "cover" and after == "open":
            return f"{label} s'est ouvert."
        if domain == "cover" and after == "closing":
            return f"{label} se ferme."
        if domain == "cover" and after == "opening":
            return f"{label} s'ouvre."
        if before is not None and after is not None:
            return f"L'état de {label} est passé de {before} à {after}."

    description = str(result.observed.get("description") or "").strip()
    if description:
        return description if description.endswith((".", "!", "?")) else f"{description}."
    return None


def _numeric_trigger_sentence(trigger: dict[str, Any]) -> str | None:
    if str(trigger.get("platform") or "") != "numeric_state":
        return None

    label = _trigger_label(trigger)
    unit = _trigger_unit(trigger)
    before = _state_value(trigger.get("from_state"))
    after = _state_value(trigger.get("to_state"))
    above = trigger.get("above")
    below = trigger.get("below")

    if above is not None:
        threshold = _format_number(above)
        if before is not None and after is not None:
            return (
                f"la valeur de « {label} » a dépassé le seuil de {threshold}{unit} "
                f"({_format_number(before)} → {_format_number(after)}{unit})"
            )
        if after is not None:
            return (
                f"la valeur de « {label} » était supérieure au seuil de {threshold}{unit} "
                f"({_format_number(after)}{unit})"
            )
        return f"la valeur de « {label} » a dépassé le seuil de {threshold}{unit}"

    if below is not None:
        threshold = _format_number(below)
        if before is not None and after is not None:
            return (
                f"la valeur de « {label} » est passée sous le seuil de {threshold}{unit} "
                f"({_format_number(before)} → {_format_number(after)}{unit})"
            )
        if after is not None:
            return (
                f"la valeur de « {label} » était inférieure au seuil de {threshold}{unit} "
                f"({_format_number(after)}{unit})"
            )
        return f"la valeur de « {label} » est passée sous le seuil de {threshold}{unit}"

    return None


def _state_trigger_sentence(trigger: dict[str, Any]) -> str | None:
    if str(trigger.get("platform") or "") != "state":
        return None
    label = _trigger_label(trigger)
    before = _state_value(trigger.get("from_state"))
    after = _state_value(trigger.get("to_state"))
    if before is not None and after is not None:
        return f"l'état de « {label} » est passé de {before} à {after}"
    if after is not None:
        return f"l'état de « {label} » est devenu {after}"
    return None


def _proven_trigger(result: InvestigationResult) -> dict[str, Any] | None:
    for step in result.chain:
        if step.get("kind") != "trigger" or step.get("proven") is not True:
            continue
        detail = step.get("detail")
        if isinstance(detail, dict):
            return detail
    return None


def _structured_human_cause(result: InvestigationResult) -> dict[str, Any] | None:
    explanation = result.meta.get("explanation")
    if not isinstance(explanation, dict):
        return None
    cause = explanation.get("human_cause")
    return cause if isinstance(cause, dict) and cause.get("proven") is True else None


def _because(reason: str) -> str:
    reason = reason.strip()
    if not reason:
        return "parce que"
    if reason[0].lower() in "aeiouyh":
        return f"parce qu'{reason}"
    return f"parce que {reason}"


def build_human_causal_answer(
    result: InvestigationResult,
    *,
    include_automation_name: bool = False,
    include_rule: bool = False,
) -> str | None:
    """Build a natural answer from evidence already proven by the engine.

    Level 1 deliberately exposes the human cause only. Level 2 may add the useful rule
    and the confirmed automation/script name. Conditions and low-level Home Assistant
    mechanics stay in the structured evidence for expert diagnosis; they are not pushed
    into the everyday answer.
    """
    if result.status != "confirmed":
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    if result.cause.get("system_confirmed") is not True:
        return None

    source_kind = str(result.cause.get("type"))
    if not any(step.get("kind") == source_kind and step.get("proven") is True for step in result.chain):
        return None

    effect = _effect_sentence(result)
    if not effect:
        return None

    structured = _structured_human_cause(result)
    reason: str | None = None
    if structured:
        reason = str(structured.get("text") or "").strip() or human_cause_text(structured)

    if not reason:
        trigger = _proven_trigger(result)
        if trigger is None:
            return None
        reason = _numeric_trigger_sentence(trigger) or _state_trigger_sentence(trigger)

    if not reason:
        return None

    effect = effect.rstrip(".")
    answer = f"{effect} {_because(reason.rstrip('.'))}."

    if include_rule and structured:
        rule = str(structured.get("rule_text") or "").strip() or human_rule_text(structured, result)
        if rule:
            answer += f" {rule.rstrip('.')}."

    if include_automation_name:
        source_name = result.cause.get("name") or result.cause.get("entity_id")
        if source_name:
            label = "Automatisation" if source_kind == "automation" else "Script"
            answer += f" {label} : « {source_name} »."
    return answer
