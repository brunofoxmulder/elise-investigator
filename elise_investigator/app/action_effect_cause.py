from __future__ import annotations

import re
from typing import Any

from causal_utils import duration_seconds, nodes, trace_detail, walk_contains
from models import InvestigationResult

_TOP_LEVEL_ACTION = re.compile(r"^action/(\d+)$")


def _executed_commands(detail: dict[str, Any], target_entity: str) -> list[dict[str, Any]]:
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return []
    out: list[dict[str, Any]] = []
    for path, raw_nodes in trace.items():
        if not str(path).startswith("action/"):
            continue
        for node in nodes(raw_nodes):
            result = node.get("result")
            params = result.get("params") if isinstance(result, dict) else None
            if not isinstance(params, dict):
                continue
            if not params.get("domain") or not params.get("service"):
                continue
            if not walk_contains(params.get("target"), target_entity):
                continue
            out.append(
                {
                    "path": str(path),
                    "domain": str(params["domain"]),
                    "service": str(params["service"]),
                    "data": params.get("service_data") or params.get("data"),
                }
            )
            break
    return out


def _same_value(actual: Any, expected: Any) -> bool:
    if actual is None or expected is None:
        return False
    if str(actual) == str(expected):
        return True
    try:
        return abs(float(actual) - float(expected)) < 1e-9
    except (TypeError, ValueError):
        return False


def _matches_effect(command: dict[str, Any], result: InvestigationResult) -> bool:
    domain = result.entity_id.split(".", 1)[0]
    if command.get("domain") != domain:
        return False
    service = str(command.get("service") or "")
    after = result.observed.get("after")
    after_text = str(after).lower() if after is not None else ""

    if domain in {"light", "switch", "fan", "input_boolean"}:
        return (after_text == "off" and service == "turn_off") or (
            after_text == "on" and service == "turn_on"
        )
    if domain == "cover":
        if after_text == "closed":
            return service == "close_cover"
        if after_text == "open":
            return service == "open_cover"
        if result.observed.get("attribute") == "current_position" and service == "set_cover_position":
            data = command.get("data")
            return _same_value(data.get("position") if isinstance(data, dict) else None, after)
    if domain == "lock":
        return (after_text == "locked" and service == "lock") or (
            after_text == "unlocked" and service == "unlock"
        )
    return False


def _config_actions(detail: dict[str, Any]) -> list[dict[str, Any]]:
    config = detail.get("config")
    if not isinstance(config, dict):
        return []
    actions = config.get("actions") or config.get("action") or config.get("sequence")
    return [item if isinstance(item, dict) else {} for item in actions] if isinstance(actions, list) else []


def _completed_wait_trigger(detail: dict[str, Any], wait_path: str) -> dict[str, Any] | None:
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None
    for node in reversed(nodes(trace.get(wait_path))):
        candidates: list[Any] = []
        result = node.get("result")
        changed = node.get("changed_variables")
        if isinstance(result, dict):
            candidates.append(result.get("wait"))
        if isinstance(changed, dict):
            candidates.append(changed.get("wait"))
        for wait in reversed(candidates):
            if not isinstance(wait, dict) or wait.get("completed") is not True:
                continue
            trigger = wait.get("trigger")
            if isinstance(trigger, dict) and trigger:
                return trigger
    return None


def _select_wait_config(wait_action: dict[str, Any], trigger: dict[str, Any]) -> dict[str, Any] | None:
    configs = wait_action.get("wait_for_trigger")
    if not isinstance(configs, list):
        return None
    configs = [item for item in configs if isinstance(item, dict)]
    try:
        idx = int(trigger.get("idx"))
        if 0 <= idx < len(configs):
            return configs[idx]
    except (TypeError, ValueError):
        pass
    return configs[0] if len(configs) == 1 else None


def _merge_trigger(trigger: dict[str, Any], config: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(trigger)
    if not isinstance(config, dict):
        return merged
    if not merged.get("platform") and config.get("trigger"):
        merged["platform"] = config["trigger"]
    for key in ("entity_id", "from", "to", "above", "below", "event", "offset", "at"):
        if merged.get(key) is None and config.get(key) is not None:
            merged[key] = config[key]
    runtime_for = merged.get("for")
    config_for = config.get("for")
    if config_for is not None:
        runtime_seconds = duration_seconds(runtime_for)
        config_seconds = duration_seconds(config_for)
        if runtime_for is None or (
            runtime_seconds is not None
            and config_seconds is not None
            and abs(runtime_seconds - config_seconds) < 1e-9
        ):
            if runtime_for is not None:
                merged["runtime_for"] = runtime_for
            merged["for"] = config_for
    return merged


def select_effect_linked_cause(result: InvestigationResult) -> dict[str, Any] | None:
    """Use the one executed command that deterministically matches the observed effect."""
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None

    commands = _executed_commands(detail, result.entity_id)
    if len(commands) < 2:
        return None
    matches = [command for command in commands if _matches_effect(command, result)]
    if len(matches) != 1:
        return None

    command_path = matches[0]["path"]
    match = _TOP_LEVEL_ACTION.fullmatch(command_path)
    actions = _config_actions(detail)
    if not match or not actions:
        return None
    command_index = int(match.group(1))
    wait_index = command_index - 1
    if not 0 <= wait_index < len(actions):
        return None
    wait_action = actions[wait_index]
    if not isinstance(wait_action.get("wait_for_trigger"), list):
        return None

    wait_path = f"action/{wait_index}"
    trigger = _completed_wait_trigger(detail, wait_path)
    if not trigger:
        return None
    config = _select_wait_config(wait_action, trigger)
    return {
        "kind": "action_trigger",
        "origin": "wait_for_trigger",
        "path": wait_path,
        "command_path": command_path,
        "proven": True,
        "detail": _merge_trigger(trigger, config),
        "effect_command": {
            "path": command_path,
            "domain": matches[0]["domain"],
            "service": matches[0]["service"],
        },
    }
