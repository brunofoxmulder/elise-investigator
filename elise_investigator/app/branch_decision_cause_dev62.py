from __future__ import annotations

from typing import Any

from branch_decision_cause import (
    _TOP_LEVEL_CHOICE,
    _action_semantics,
    _choice_result,
    _config_actions,
    _nearest_executed_branch_action,
    _previous_delay_seconds,
    _runtime_result,
    select_branch_decision_cause as select_legacy_branch_decision_cause,
)
from causal_utils import nodes, trace_detail
from models import InvestigationResult


def _true_condition_detail(config: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any] | None:
    condition_type = str(config.get("condition") or "")
    if condition_type == "numeric_state":
        detail = {
            "platform": "numeric_state",
            "entity_id": config.get("entity_id"),
            "above": config.get("above"),
            "below": config.get("below"),
            "actual": runtime.get("state"),
            "condition_result": True,
        }
        if detail["entity_id"] and (detail["above"] is not None or detail["below"] is not None):
            return detail
    if condition_type == "state":
        detail = {
            "platform": "state",
            "entity_id": config.get("entity_id"),
            "to": config.get("state"),
            "actual": runtime.get("state"),
            "condition_result": True,
        }
        if detail["entity_id"] and detail["to"] is not None:
            return detail
    return None


def _single_true_chosen_condition(
    detail: dict[str, Any], action_index: int, choice: str | int
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    if str(choice) == "default":
        return None
    try:
        choice_index = int(choice)
    except (TypeError, ValueError):
        return None

    actions = _config_actions(detail)
    if not 0 <= action_index < len(actions):
        return None
    choices = actions[action_index].get("choose")
    if not isinstance(choices, list) or not 0 <= choice_index < len(choices):
        return None
    selected = choices[choice_index]
    if not isinstance(selected, dict):
        return None

    conditions = selected.get("conditions")
    if isinstance(conditions, dict):
        conditions = [conditions]
    if not isinstance(conditions, list) or len(conditions) != 1 or not isinstance(conditions[0], dict):
        return None

    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None
    branch_path = f"action/{action_index}/choose/{choice_index}"
    branch_true = False
    for node in nodes(trace.get(branch_path)):
        result = node.get("result")
        if isinstance(result, dict) and result.get("result") is True:
            branch_true = True
            break
    if not branch_true:
        return None

    condition_path = f"{branch_path}/conditions/0"
    runtime = _runtime_result(detail, condition_path)
    if not isinstance(runtime, dict):
        return None
    return conditions[0], runtime, condition_path


def select_branch_decision_cause(result: InvestigationResult) -> dict[str, Any] | None:
    """Prefer the runtime-proven chosen branch that led to the target action.

    dev.62 adds one narrow case to the existing conservative branch selector:
    a choose branch is accepted only when HA's exact trace proves which branch was
    selected, that branch has exactly one supported condition, and the executed
    action in that same branch matches the investigated effect. Otherwise the
    validated legacy selector is used unchanged.
    """
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None

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

        proven = _single_true_chosen_condition(detail, action_index, choice)
        if not proven:
            continue
        condition_config, runtime, condition_path = proven
        condition = _true_condition_detail(condition_config, runtime)
        if not condition:
            continue

        delay_seconds = _previous_delay_seconds(detail, action_index)
        if delay_seconds is not None:
            condition["delay_seconds"] = delay_seconds

        domain, service = _action_semantics(config_action)
        return {
            "kind": "branch_decision",
            "origin": "choose_condition",
            "path": condition_path,
            "command_path": command_path,
            "proven": True,
            "detail": condition,
            "effect_command": {
                "path": command_path,
                "domain": domain or result.entity_id.split(".", 1)[0],
                "service": service,
            },
        }

    return select_legacy_branch_decision_cause(result)
