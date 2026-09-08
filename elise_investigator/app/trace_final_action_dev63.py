from __future__ import annotations

from typing import Any

from action_effect_cause import _config_actions, _executed_commands, _matches_effect
from branch_decision_cause import (
    _TOP_LEVEL_CHOICE,
    _action_semantics,
    _choice_result,
    _nearest_executed_branch_action,
    _runtime_result,
)
from causal_utils import duration_seconds, duration_text, nodes, trace_detail
from models import InvestigationResult


def _wait_runtime(detail: dict[str, Any], path: str) -> dict[str, Any] | None:
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None
    for node in reversed(nodes(trace.get(path))):
        candidates: list[Any] = []
        result = node.get("result")
        changed = node.get("changed_variables")
        variables = node.get("variables")
        if isinstance(result, dict):
            candidates.append(result.get("wait"))
        if isinstance(changed, dict):
            candidates.append(changed.get("wait"))
        if isinstance(variables, dict):
            candidates.append(variables.get("wait"))
        for wait in reversed(candidates):
            if isinstance(wait, dict) and "completed" in wait:
                return wait
    return None


def select_wait_timeout_cause(result: InvestigationResult) -> dict[str, Any] | None:
    """Return a proven wait timeout immediately releasing the target command.

    This is deliberately narrow: one executed command must match the observed effect,
    the immediately preceding top-level action must be wait_for_trigger with a timeout,
    and HA's exact trace must expose wait.completed == False. No temporal correlation.
    """
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None

    commands = _executed_commands(detail, result.entity_id)
    matches = [command for command in commands if _matches_effect(command, result)]
    if len(matches) != 1:
        return None
    path = str(matches[0].get("path") or "")
    parts = path.split("/")
    if len(parts) != 2 or parts[0] != "action":
        return None
    try:
        command_index = int(parts[1])
    except ValueError:
        return None

    actions = _config_actions(detail)
    wait_index = command_index - 1
    if not 0 <= wait_index < len(actions):
        return None
    wait_action = actions[wait_index]
    if not isinstance(wait_action.get("wait_for_trigger"), list):
        return None
    timeout = wait_action.get("timeout")
    seconds = duration_seconds(timeout)
    if seconds is None or seconds <= 0:
        return None

    wait_path = f"action/{wait_index}"
    runtime = _wait_runtime(detail, wait_path)
    if not isinstance(runtime, dict) or runtime.get("completed") is not False:
        return None

    return {
        "kind": "action_trigger",
        "origin": "wait_timeout",
        "path": wait_path,
        "command_path": path,
        "proven": True,
        "detail": {
            "platform": "wait_timeout",
            "timeout": timeout,
            "timeout_seconds": seconds,
            "duration_text": duration_text(seconds),
        },
        "effect_command": {
            "path": path,
            "domain": matches[0].get("domain"),
            "service": matches[0].get("service"),
        },
    }


def _supported_true_condition(config: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any] | None:
    condition_type = str(config.get("condition") or "")
    entity_id = config.get("entity_id")
    if isinstance(entity_id, list):
        if len(entity_id) != 1:
            return None
        entity_id = entity_id[0]
    if not isinstance(entity_id, str) or not entity_id:
        return None
    if condition_type == "numeric_state":
        above = config.get("above")
        below = config.get("below")
        if above is None and below is None:
            return None
        return {
            "platform": "numeric_state",
            "entity_id": entity_id,
            "above": above,
            "below": below,
            "actual": runtime.get("state"),
            "condition_result": True,
        }
    if condition_type == "state" and config.get("state") is not None:
        return {
            "platform": "state",
            "entity_id": entity_id,
            "to": config.get("state"),
            "actual": runtime.get("state"),
            "condition_result": True,
        }
    return None


def select_chosen_branch_conditions(result: InvestigationResult) -> dict[str, Any] | None:
    """Return every runtime-proven supported condition of the chosen target branch.

    dev.63 extends dev.62 from exactly one condition to a small conjunction (max 4).
    Every condition must be supported and proven true; otherwise it fails closed.
    """
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    detail = trace_detail(result)
    if not isinstance(detail, dict) or not isinstance(detail.get("trace"), dict):
        return None

    actions = _config_actions(detail)
    trace = detail["trace"]
    for path in trace:
        match = _TOP_LEVEL_CHOICE.fullmatch(str(path))
        if not match:
            continue
        action_index = int(match.group(1))
        choice = _choice_result(detail, action_index)
        if choice is None or str(choice) == "default":
            continue
        effect_action = _nearest_executed_branch_action(detail, result, action_index, choice)
        if not effect_action:
            continue
        command_path, config_action = effect_action
        try:
            choice_index = int(choice)
        except (TypeError, ValueError):
            continue
        if not 0 <= action_index < len(actions):
            continue
        choices = actions[action_index].get("choose")
        if not isinstance(choices, list) or not 0 <= choice_index < len(choices):
            continue
        selected = choices[choice_index]
        if not isinstance(selected, dict):
            continue
        conditions = selected.get("conditions")
        if isinstance(conditions, dict):
            conditions = [conditions]
        if not isinstance(conditions, list) or not 1 <= len(conditions) <= 4:
            continue

        branch_path = f"action/{action_index}/choose/{choice_index}"
        branch_true = any(
            isinstance(node.get("result"), dict) and node["result"].get("result") is True
            for node in nodes(trace.get(branch_path))
        )
        if not branch_true:
            continue

        proven: list[dict[str, Any]] = []
        for condition_index, condition in enumerate(conditions):
            if not isinstance(condition, dict):
                proven = []
                break
            condition_path = f"{branch_path}/conditions/{condition_index}"
            runtime = _runtime_result(detail, condition_path)
            if not isinstance(runtime, dict):
                proven = []
                break
            item = _supported_true_condition(condition, runtime)
            if not item:
                proven = []
                break
            item["path"] = condition_path
            proven.append(item)
        if not proven:
            continue

        domain, service = _action_semantics(config_action)
        return {
            "kind": "branch_decision",
            "origin": "choose_conditions",
            "path": branch_path,
            "command_path": command_path,
            "proven": True,
            "detail": {"conditions": proven},
            "effect_command": {
                "path": command_path,
                "domain": domain or result.entity_id.split(".", 1)[0],
                "service": service,
            },
        }
    return None
