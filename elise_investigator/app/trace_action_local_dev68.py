from __future__ import annotations

import re
from typing import Any

from action_effect_cause import (
    _completed_wait_trigger,
    _config_actions,
    _executed_commands,
    _matches_effect,
    _merge_trigger,
    _select_wait_config,
)
from causal_utils import duration_seconds, duration_text, nodes, trace_detail
from human_cause import _proven_start_trigger
from models import InvestigationResult
from trace_final_action_dev63 import _supported_true_condition

_TOP_LEVEL_ACTION = re.compile(r"^action/(\d+)$")


def _unique_effect_command(result: InvestigationResult) -> dict[str, Any] | None:
    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None
    matches = [
        command
        for command in _executed_commands(detail, result.entity_id)
        if _matches_effect(command, result)
    ]
    return matches[0] if len(matches) == 1 else None


def select_completed_wait_cause(result: InvestigationResult) -> dict[str, Any] | None:
    """Explain a target action released by one completed top-level wait_for_trigger.

    Unlike the older selector, this does not require a second command on the same target.
    The exact trace, a unique target effect command and adjacency in the automation action
    list remain mandatory. No time-window inference is used.
    """
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    detail = trace_detail(result)
    command = _unique_effect_command(result)
    if not isinstance(detail, dict) or not isinstance(command, dict):
        return None
    match = _TOP_LEVEL_ACTION.fullmatch(str(command.get("path") or ""))
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
    actual = _completed_wait_trigger(detail, wait_path)
    if not actual:
        return None
    config = _select_wait_config(wait_action, actual)
    return {
        "kind": "action_trigger",
        "origin": "wait_for_trigger",
        "path": wait_path,
        "command_path": command["path"],
        "proven": True,
        "detail": _merge_trigger(actual, config),
        "effect_command": {
            "path": command["path"],
            "domain": command.get("domain"),
            "service": command.get("service"),
        },
    }


def select_elapsed_delay_cause(result: InvestigationResult) -> dict[str, Any] | None:
    """Explain a target action immediately following one executed top-level delay."""
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    detail = trace_detail(result)
    command = _unique_effect_command(result)
    if not isinstance(detail, dict) or not isinstance(command, dict):
        return None
    match = _TOP_LEVEL_ACTION.fullmatch(str(command.get("path") or ""))
    actions = _config_actions(detail)
    trace = detail.get("trace")
    if not match or not actions or not isinstance(trace, dict):
        return None
    command_index = int(match.group(1))
    delay_index = command_index - 1
    if not 0 <= delay_index < len(actions):
        return None
    delay_action = actions[delay_index]
    delay = delay_action.get("delay")
    seconds = duration_seconds(delay)
    if seconds is None or seconds <= 0:
        return None
    delay_path = f"action/{delay_index}"
    if not nodes(trace.get(delay_path)):
        return None
    return {
        "kind": "action_trigger",
        "origin": "delay_elapsed",
        "path": delay_path,
        "command_path": command["path"],
        "proven": True,
        "detail": {
            "platform": "delay_elapsed",
            "delay": delay,
            "delay_seconds": seconds,
            "duration_text": duration_text(seconds),
        },
        "effect_command": {
            "path": command["path"],
            "domain": command.get("domain"),
            "service": command.get("service"),
        },
    }


def select_trigger_with_true_conditions(result: InvestigationResult) -> dict[str, Any] | None:
    """Return start trigger + all proven top-level conditions when jointly required.

    This covers the common HA shape `trigger -> conditions -> action` without treating
    arbitrary guards elsewhere in a trace as causal. At most four supported conditions
    are accepted and every one must be proven true by the exact trace.
    """
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    detail = trace_detail(result)
    command = _unique_effect_command(result)
    if not isinstance(detail, dict) or not isinstance(command, dict):
        return None
    config = detail.get("config")
    trace = detail.get("trace")
    if not isinstance(config, dict) or not isinstance(trace, dict):
        return None
    raw_conditions = config.get("conditions") or config.get("condition")
    if isinstance(raw_conditions, dict):
        conditions = [raw_conditions]
    elif isinstance(raw_conditions, list):
        conditions = raw_conditions
    else:
        return None
    if not 1 <= len(conditions) <= 4:
        return None

    proven: list[dict[str, Any]] = []
    for index, condition in enumerate(conditions):
        if not isinstance(condition, dict):
            return None
        runtime = None
        for node in reversed(nodes(trace.get(f"condition/{index}"))):
            candidate = node.get("result")
            if isinstance(candidate, dict):
                runtime = candidate
                break
        if not isinstance(runtime, dict) or runtime.get("result") is not True:
            return None
        runtime_detail = dict(runtime)
        variables = runtime_detail.get("variables")
        if isinstance(variables, dict) and runtime_detail.get("state") is None:
            runtime_detail.update({k: v for k, v in variables.items() if k not in runtime_detail})
        item = _supported_true_condition(condition, runtime_detail)
        if not item:
            return None
        item["path"] = f"condition/{index}"
        proven.append(item)

    trigger = _proven_start_trigger(result)
    if not isinstance(trigger, dict) or not trigger:
        return None
    return {
        "kind": "required_conditions",
        "origin": "trigger_plus_conditions",
        "path": "trigger+condition",
        "command_path": command["path"],
        "proven": True,
        "detail": {"trigger": dict(trigger), "conditions": proven},
        "effect_command": {
            "path": command["path"],
            "domain": command.get("domain"),
            "service": command.get("service"),
        },
    }
