from __future__ import annotations

import re
from typing import Any

from causal_utils import (
    device_class,
    duration_seconds,
    duration_text,
    friendly_name,
    nodes,
    normalize_text,
    number_text,
    state_value,
    trace_detail,
    unit,
    walk_contains,
)
from models import InvestigationResult


_TOP_LEVEL_ACTION = re.compile(r"^action/(\d+)$")


def _command_paths(detail: dict[str, Any], target_entity: str) -> list[str]:
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return []

    paths: list[str] = []
    for path, raw_nodes in trace.items():
        path_text = str(path)
        if not path_text.startswith("action/"):
            continue
        for node in nodes(raw_nodes):
            result = node.get("result")
            if not isinstance(result, dict):
                continue
            params = result.get("params")
            if not isinstance(params, dict):
                continue
            if not params.get("domain") or not params.get("service"):
                continue
            if walk_contains(params.get("target"), target_entity):
                paths.append(path_text)
                break

    return list(dict.fromkeys(paths))


def _config_actions(detail: dict[str, Any]) -> list[dict[str, Any]]:
    config = detail.get("config")
    if not isinstance(config, dict):
        return []
    for key in ("actions", "action", "sequence"):
        value = config.get(key)
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {} for item in value]
    return []


def _wait_result(node: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[Any] = []
    result = node.get("result")
    if isinstance(result, dict):
        candidates.append(result.get("wait"))
    changed = node.get("changed_variables")
    if isinstance(changed, dict):
        candidates.append(changed.get("wait"))
    variables = node.get("variables")
    if isinstance(variables, dict):
        candidates.append(variables.get("wait"))

    for candidate in reversed(candidates):
        if not isinstance(candidate, dict):
            continue
        trigger = candidate.get("trigger")
        if candidate.get("completed") is True and isinstance(trigger, dict) and trigger:
            return candidate
    return None


def _completed_wait_trigger(detail: dict[str, Any], path: str) -> dict[str, Any] | None:
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None
    for node in reversed(nodes(trace.get(path))):
        wait = _wait_result(node)
        if wait:
            trigger = wait.get("trigger")
            return trigger if isinstance(trigger, dict) else None
    return None


def _select_wait_config(wait_action: dict[str, Any], actual_trigger: dict[str, Any]) -> dict[str, Any] | None:
    raw = wait_action.get("wait_for_trigger")
    if not isinstance(raw, list) or not raw:
        return None
    configs = [item for item in raw if isinstance(item, dict)]
    if not configs:
        return None

    idx = actual_trigger.get("idx")
    try:
        if idx is not None and 0 <= int(idx) < len(configs):
            return configs[int(idx)]
    except (TypeError, ValueError):
        pass

    trigger_id = actual_trigger.get("id")
    if trigger_id is not None:
        for config in configs:
            if str(config.get("id")) == str(trigger_id):
                return config

    return configs[0] if len(configs) == 1 else None


def _merge_trigger_config(actual: dict[str, Any], config: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(actual)
    if not isinstance(config, dict):
        return merged
    if "platform" not in merged and config.get("trigger"):
        merged["platform"] = config.get("trigger")
    for key in (
        "entity_id",
        "from",
        "to",
        "for",
        "above",
        "below",
        "event",
        "offset",
        "at",
    ):
        if merged.get(key) is None and config.get(key) is not None:
            merged[key] = config.get(key)
    return merged


def _proven_start_trigger(result: InvestigationResult) -> dict[str, Any] | None:
    for step in result.chain:
        if step.get("kind") != "trigger" or step.get("proven") is not True:
            continue
        detail = step.get("detail")
        if isinstance(detail, dict) and detail:
            return detail
    return None


def select_human_cause(result: InvestigationResult) -> dict[str, Any] | None:
    """Select the proven event that best explains the observed action.

    An automation's initial trigger is not always the cause of the action being
    investigated. A later ``wait_for_trigger`` can be the event that releases the exact
    command that changed the target. The first implementation intentionally supports only
    the strongest unambiguous shape: a completed top-level wait immediately followed by
    the executed top-level command targeting the investigated entity. Nested or ambiguous
    paths fall back to the already-proven automation trigger instead of guessing.
    """
    if result.status != "confirmed":
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    if result.cause.get("system_confirmed") is not True:
        return None

    detail = trace_detail(result)
    if isinstance(detail, dict):
        command_paths = _command_paths(detail, result.entity_id)
        if len(command_paths) == 1:
            match = _TOP_LEVEL_ACTION.fullmatch(command_paths[0])
            actions = _config_actions(detail)
            if match and actions:
                command_index = int(match.group(1))
                wait_index = command_index - 1
                if 0 <= wait_index < len(actions):
                    wait_action = actions[wait_index]
                    if isinstance(wait_action.get("wait_for_trigger"), list):
                        wait_path = f"action/{wait_index}"
                        actual = _completed_wait_trigger(detail, wait_path)
                        if actual:
                            config = _select_wait_config(wait_action, actual)
                            return {
                                "kind": "action_trigger",
                                "origin": "wait_for_trigger",
                                "path": wait_path,
                                "command_path": command_paths[0],
                                "proven": True,
                                "detail": _merge_trigger_config(actual, config),
                            }

    trigger = _proven_start_trigger(result)
    if trigger:
        return {
            "kind": "automation_trigger",
            "origin": "automation_trigger",
            "path": "trigger",
            "proven": True,
            "detail": dict(trigger),
        }
    return None


def _numeric_subject(label: str, unit_name: str) -> str:
    label_norm = normalize_text(label)
    unit_norm = normalize_text(unit_name)
    if "temperature exterieure" in label_norm:
        return "la température extérieure"
    if unit_norm == "w" or "power" in label_norm or "puissance" in label_norm:
        return "la puissance mesurée"
    return f"la valeur de « {label} »"


def human_cause_text(cause: dict[str, Any]) -> str | None:
    detail = cause.get("detail")
    if not isinstance(detail, dict):
        return None

    platform = str(detail.get("platform") or detail.get("trigger") or "").lower()
    label = friendly_name(cause)
    label_norm = normalize_text(label)

    if platform == "sun":
        event = str(detail.get("event") or "").lower()
        if event == "sunset":
            return "le soleil s'est couché"
        if event == "sunrise":
            return "le soleil s'est levé"

    if platform == "numeric_state":
        above = detail.get("above")
        below = detail.get("below")
        unit_name = unit(cause)
        suffix = f" {unit_name}" if unit_name else ""
        subject = _numeric_subject(label, unit_name)
        condition_result = detail.get("condition_result")
        actual = detail.get("actual")
        delay = duration_text(duration_seconds(detail.get("delay_seconds")))
        prefix = f"après {delay}, " if delay else ""

        if condition_result is False and above is not None:
            threshold = number_text(above)
            if actual is not None:
                return (
                    f"{prefix}{subject} était de {number_text(actual)}{suffix} "
                    f"et ne dépassait pas {threshold}{suffix}"
                )
            return f"{prefix}{subject} ne dépassait pas {threshold}{suffix}"
        if condition_result is False and below is not None:
            threshold = number_text(below)
            if actual is not None:
                return (
                    f"{prefix}{subject} était de {number_text(actual)}{suffix} "
                    f"et n'était pas inférieure à {threshold}{suffix}"
                )
            return f"{prefix}{subject} n'était pas inférieure à {threshold}{suffix}"

        if above is not None:
            return f"{subject} dépassait {number_text(above)}{suffix}"
        if below is not None:
            return f"{subject} était inférieure à {number_text(below)}{suffix}"

    if platform == "state":
        after = state_value(detail.get("to_state"))
        if after is None:
            after = detail.get("to")
        klass = normalize_text(device_class(cause))

        motion_like = klass in {"motion", "occupancy"} or "mouvement" in label_norm
        presence_like = klass == "presence" or "presence" in label_norm
        if motion_like:
            if str(after).lower() == "on":
                return "un mouvement a été détecté"
            if str(after).lower() == "off":
                return "il n'y avait plus de mouvement"
        if presence_like:
            if str(after).lower() == "on":
                return "une présence a été détectée"
            if str(after).lower() == "off":
                return "il n'y avait plus de présence"
        if klass == "window" or "fenetre" in label_norm:
            if str(after).lower() == "off":
                return "la fenêtre a été refermée"
            if str(after).lower() == "on":
                return "la fenêtre a été ouverte"
        if klass == "door" or "porte" in label_norm:
            if str(after).lower() == "off":
                return "la porte a été refermée"
            if str(after).lower() == "on":
                return "la porte a été ouverte"
        if after is not None:
            return f"« {label} » est passé à {after}"

    if platform == "time":
        return "l'heure prévue est arrivée"

    return None


def human_rule_text(cause: dict[str, Any], result: InvestigationResult) -> str | None:
    detail = cause.get("detail")
    if not isinstance(detail, dict):
        return None

    platform = str(detail.get("platform") or detail.get("trigger") or "").lower()
    domain = result.entity_id.split(".", 1)[0]
    after = result.observed.get("after")

    if cause.get("origin") == "wait_for_trigger":
        duration = duration_text(duration_seconds(detail.get("for")))
        if duration and platform == "state":
            simple = human_cause_text(cause) or ""
            if domain == "light" and after == "off" and "mouvement" in simple:
                return f"La règle prévoit l'extinction après {duration} sans mouvement"
            return f"La règle attend {duration} avant d'exécuter l'action"

    if platform == "sun":
        event = str(detail.get("event") or "").lower()
        offset = duration_text(abs(duration_seconds(detail.get("offset")) or 0))
        if event == "sunset" and offset and domain == "cover":
            return f"La règle prévoit la fermeture {offset} après le coucher du soleil"
        if event == "sunrise" and offset and domain == "cover":
            return f"La règle prévoit l'action sur le volet {offset} après le lever du soleil"

    return None
