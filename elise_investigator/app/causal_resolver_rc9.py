from __future__ import annotations

from typing import Any

from causal_resolver_v2 import _matches_effect_v2, resolve_cause as resolve_cause_v2, unique_effect_command as unique_effect_command_v2
from causal_utils import duration_seconds, duration_text, nodes, trace_detail, walk_contains
from models import InvestigationResult
from trace_branch_path_dev70 import _config_at_path


def _explicit_other_entity(target: Any, wanted: str) -> bool:
    """True only when HA exposes a concrete entity_id that is explicitly another entity."""
    if target is None:
        return False
    stack = [target]
    seen_entity = False
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "entity_id":
                    values = child if isinstance(child, list) else [child]
                    for item in values:
                        text = str(item or "")
                        if "." in text:
                            seen_entity = True
                            if text == wanted:
                                return False
                else:
                    stack.append(child)
        elif isinstance(value, list):
            stack.extend(value)
    return seen_entity


def _all_runtime_commands(detail: dict[str, Any], target_entity: str) -> list[dict[str, Any]]:
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return []
    exact: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for path, raw_nodes in trace.items():
        if not str(path).startswith("action/"):
            continue
        for node in nodes(raw_nodes):
            result = node.get("result")
            params = result.get("params") if isinstance(result, dict) else None
            if not isinstance(params, dict) or not params.get("domain") or not params.get("service"):
                continue
            command = {
                "path": str(path),
                "domain": str(params["domain"]),
                "service": str(params["service"]),
                "data": params.get("service_data") or params.get("data"),
            }
            target = params.get("target")
            if walk_contains(target, target_entity):
                exact.append(command)
            elif not _explicit_other_entity(target, target_entity):
                # Device actions can resolve through device/registry ids and omit the
                # concrete entity_id from trace params. Keep them only as an unresolved
                # fallback; explicit commands to another entity are never borrowed.
                unresolved.append(command)
            break
    return exact if exact else unresolved


def unique_effect_command_rc9(result: InvestigationResult) -> dict[str, Any] | None:
    command = unique_effect_command_v2(result)
    if isinstance(command, dict):
        return command
    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None
    matches = [
        item
        for item in _all_runtime_commands(detail, result.entity_id)
        if _matches_effect_v2(item, result)
    ]
    return matches[0] if len(matches) == 1 else None


def _previous_sibling(path: str) -> str | None:
    parts = [part for part in str(path).split("/") if part]
    if not parts:
        return None
    try:
        index = int(parts[-1])
    except ValueError:
        return None
    if index <= 0:
        return None
    return "/".join(parts[:-1] + [str(index - 1)])


def _executed(trace: dict[str, Any], path: str) -> bool:
    return bool(nodes(trace.get(path)))


def _adjacent_delay(result: InvestigationResult, command: dict[str, Any]) -> dict[str, Any] | None:
    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None
    config = detail.get("config")
    trace = detail.get("trace")
    if not isinstance(config, dict) or not isinstance(trace, dict):
        return None
    command_path = str(command.get("path") or "")
    previous_path = _previous_sibling(command_path)
    if not previous_path:
        return None
    previous = _config_at_path(config, previous_path)
    if not isinstance(previous, dict) or "delay" not in previous or not _executed(trace, previous_path):
        return None
    seconds = duration_seconds(previous.get("delay"))
    if seconds is None or seconds <= 0:
        return None
    return {
        "kind": "action_trigger",
        "origin": "delay_elapsed",
        "path": previous_path,
        "command_path": command_path,
        "proven": True,
        "detail": {
            "platform": "delay_elapsed",
            "delay": previous.get("delay"),
            "delay_seconds": seconds,
            "duration_text": duration_text(seconds),
        },
        "effect_command": {
            "path": command_path,
            "domain": command.get("domain"),
            "service": command.get("service"),
        },
    }


def _default_failed_condition(result: InvestigationResult, command: dict[str, Any]) -> dict[str, Any] | None:
    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None
    config = detail.get("config")
    trace = detail.get("trace")
    if not isinstance(config, dict) or not isinstance(trace, dict):
        return None
    path = str(command.get("path") or "")
    parts = path.split("/")
    if len(parts) < 4 or parts[0] != "action" or parts[2] != "default":
        return None
    try:
        action_index = int(parts[1])
    except ValueError:
        return None
    action = _config_at_path(config, f"action/{action_index}")
    if not isinstance(action, dict):
        return None
    choices = action.get("choose")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return None
    conditions = choices[0].get("conditions")
    if not isinstance(conditions, list) or len(conditions) != 1 or not isinstance(conditions[0], dict):
        return None
    condition = conditions[0]
    platform = str(condition.get("condition") or condition.get("platform") or "").casefold()
    if platform != "numeric_state":
        return None

    # Home Assistant records `choice: default` on the executed choose action. This is
    # direct proof that the sole configured condition did not select its branch.
    default_proven = False
    for node in nodes(trace.get(f"action/{action_index}")):
        result_node = node.get("result")
        if isinstance(result_node, dict) and str(result_node.get("choice") or "").casefold() == "default":
            default_proven = True
            break
    if not default_proven:
        return None

    payload: dict[str, Any] = {
        "platform": "choose_default_failed_condition",
        "condition": dict(condition),
    }
    previous_top = _config_at_path(config, f"action/{action_index - 1}") if action_index > 0 else None
    if isinstance(previous_top, dict) and "delay" in previous_top and _executed(trace, f"action/{action_index - 1}"):
        seconds = duration_seconds(previous_top.get("delay"))
        if seconds is not None and seconds > 0:
            payload["prior_delay_seconds"] = seconds
            payload["prior_delay_text"] = duration_text(seconds)

    return {
        "kind": "branch_default",
        "origin": "choose_default_failed_condition",
        "path": f"action/{action_index}",
        "command_path": path,
        "proven": True,
        "detail": payload,
        "effect_command": {
            "path": path,
            "domain": command.get("domain"),
            "service": command.get("service"),
        },
    }


def resolve_cause_rc9(result: InvestigationResult) -> dict[str, Any] | None:
    # Preserve every V2 result that is already proven and validated on terrain.
    existing = resolve_cause_v2(result)
    if isinstance(existing, dict):
        return existing

    command = unique_effect_command_rc9(result)
    if not isinstance(command, dict):
        return None

    default = _default_failed_condition(result, command)
    if isinstance(default, dict):
        return default

    delay = _adjacent_delay(result, command)
    if isinstance(delay, dict):
        return delay

    return None
