from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from causal_utils import nodes, trace_detail, walk_contains
from models import InvestigationResult

_TOP_LEVEL_CHOICE = re.compile(r"^action/(\d+)$")
_DEFAULT_ACTION = re.compile(r"^action/(\d+)/default/(\d+)$")
_SEQUENCE_ACTION = re.compile(r"^action/(\d+)/choose/(\d+)/sequence/(\d+)$")
_BRANCH_EVENT_GRACE_SECONDS = 5.0


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _node_time(node: dict[str, Any]) -> datetime | None:
    return _dt(node.get("timestamp"))


def _config_actions(detail: dict[str, Any]) -> list[dict[str, Any]]:
    config = detail.get("config")
    if not isinstance(config, dict):
        return []
    for key in ("actions", "action", "sequence"):
        raw = config.get(key)
        if isinstance(raw, list):
            return [item if isinstance(item, dict) else {} for item in raw]
    return []


def _choice_result(detail: dict[str, Any], action_index: int) -> str | int | None:
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None
    for node in reversed(nodes(trace.get(f"action/{action_index}"))):
        result = node.get("result")
        if isinstance(result, dict) and result.get("choice") is not None:
            return result.get("choice")
    return None


def _configured_action(detail: dict[str, Any], runtime_path: str) -> dict[str, Any] | None:
    actions = _config_actions(detail)
    default = _DEFAULT_ACTION.fullmatch(runtime_path)
    if default:
        action_index, sequence_index = map(int, default.groups())
        if not 0 <= action_index < len(actions):
            return None
        branch = actions[action_index].get("default")
        if isinstance(branch, list) and 0 <= sequence_index < len(branch):
            item = branch[sequence_index]
            return item if isinstance(item, dict) else None
        return None

    chosen = _SEQUENCE_ACTION.fullmatch(runtime_path)
    if chosen:
        action_index, choice_index, sequence_index = map(int, chosen.groups())
        if not 0 <= action_index < len(actions):
            return None
        choices = actions[action_index].get("choose")
        if not isinstance(choices, list) or not 0 <= choice_index < len(choices):
            return None
        choice = choices[choice_index]
        sequence = choice.get("sequence") if isinstance(choice, dict) else None
        if isinstance(sequence, list) and 0 <= sequence_index < len(sequence):
            item = sequence[sequence_index]
            return item if isinstance(item, dict) else None
    return None


def _action_targets_result(config_action: dict[str, Any], result: InvestigationResult) -> bool:
    if walk_contains(config_action.get("target"), result.entity_id):
        return True
    if str(config_action.get("entity_id") or "") == result.entity_id:
        return True

    identity = result.meta.get("identity") if isinstance(result.meta, dict) else None
    target_device = str(identity.get("device_id") or "") if isinstance(identity, dict) else ""
    return bool(target_device and str(config_action.get("device_id") or "") == target_device)


def _action_semantics(config_action: dict[str, Any]) -> tuple[str, str]:
    domain = str(config_action.get("domain") or "")
    action = str(config_action.get("action") or config_action.get("service") or "")
    action_type = str(config_action.get("type") or "")
    if "." in action:
        action_domain, service = action.split(".", 1)
        return action_domain, service
    return domain, action_type or action


def _action_matches_effect(config_action: dict[str, Any], result: InvestigationResult) -> bool:
    if not _action_targets_result(config_action, result):
        return False
    domain, service = _action_semantics(config_action)
    target_domain = result.entity_id.split(".", 1)[0]
    if domain and domain != target_domain:
        return False

    after = str(result.observed.get("after") or "").lower()
    if target_domain in {"light", "switch", "fan", "input_boolean"}:
        return (after == "off" and service == "turn_off") or (after == "on" and service == "turn_on")
    if target_domain == "cover":
        return (after == "closed" and service == "close_cover") or (after == "open" and service == "open_cover")
    if target_domain == "lock":
        return (after == "locked" and service == "lock") or (after == "unlocked" and service == "unlock")
    return False


def _nearest_executed_branch_action(
    detail: dict[str, Any],
    result: InvestigationResult,
    action_index: int,
    choice: str | int,
) -> tuple[str, dict[str, Any]] | None:
    trace = detail.get("trace")
    event_time = _dt(result.event_time)
    if not isinstance(trace, dict) or event_time is None:
        return None

    if str(choice) == "default":
        prefix = f"action/{action_index}/default/"
    else:
        prefix = f"action/{action_index}/choose/{choice}/sequence/"

    candidates: list[tuple[float, str, dict[str, Any]]] = []
    for path, raw_nodes in trace.items():
        path_text = str(path)
        if not path_text.startswith(prefix):
            continue
        config_action = _configured_action(detail, path_text)
        if not isinstance(config_action, dict) or not _action_matches_effect(config_action, result):
            continue
        for node in nodes(raw_nodes):
            when = _node_time(node)
            if when is None or when > event_time:
                continue
            distance = (event_time - when).total_seconds()
            if distance <= _BRANCH_EVENT_GRACE_SECONDS:
                candidates.append((distance, path_text, config_action))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    best = candidates[0]
    if len(candidates) > 1 and abs(candidates[1][0] - best[0]) < 1e-9:
        return None
    return best[1], best[2]


def _runtime_result(detail: dict[str, Any], prefix: str) -> dict[str, Any] | None:
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None
    matches: list[tuple[int, dict[str, Any]]] = []
    for path, raw_nodes in trace.items():
        path_text = str(path)
        if path_text != prefix and not path_text.startswith(prefix + "/"):
            continue
        for node in nodes(raw_nodes):
            result = node.get("result")
            if not isinstance(result, dict):
                continue
            if any(key in result for key in ("state", "wanted_state", "wanted_state_above", "wanted_state_below")):
                matches.append((path_text.count("/"), result))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _single_failed_default_condition(
    detail: dict[str, Any], action_index: int
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    actions = _config_actions(detail)
    if not 0 <= action_index < len(actions):
        return None
    choose = actions[action_index].get("choose")
    if not isinstance(choose, list) or len(choose) != 1 or not isinstance(choose[0], dict):
        return None

    conditions = choose[0].get("conditions")
    if isinstance(conditions, dict):
        conditions = [conditions]
    if not isinstance(conditions, list) or len(conditions) != 1 or not isinstance(conditions[0], dict):
        return None

    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None
    branch_path = f"action/{action_index}/choose/0"
    branch_false = False
    for node in nodes(trace.get(branch_path)):
        result = node.get("result")
        if isinstance(result, dict) and result.get("result") is False:
            branch_false = True
            break
    if not branch_false:
        return None

    condition_path = f"{branch_path}/conditions/0"
    runtime = _runtime_result(detail, condition_path)
    if not isinstance(runtime, dict):
        return None
    return conditions[0], runtime, condition_path


def _previous_delay_seconds(detail: dict[str, Any], action_index: int) -> float | None:
    if action_index <= 0:
        return None
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None
    for node in reversed(nodes(trace.get(f"action/{action_index - 1}"))):
        result = node.get("result")
        if not isinstance(result, dict) or result.get("done") is not True:
            continue
        try:
            return float(result.get("delay"))
        except (TypeError, ValueError):
            return None
    return None


def _condition_detail(config: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any] | None:
    condition_type = str(config.get("condition") or "")
    if condition_type == "numeric_state":
        detail = {
            "platform": "numeric_state",
            "entity_id": config.get("entity_id"),
            "above": config.get("above"),
            "below": config.get("below"),
            "actual": runtime.get("state"),
            "condition_result": False,
        }
        if detail["entity_id"] and (detail["above"] is not None or detail["below"] is not None):
            return detail
    if condition_type == "state":
        return {
            "platform": "state",
            "entity_id": config.get("entity_id"),
            "to": config.get("state"),
            "actual": runtime.get("state"),
            "condition_result": False,
        }
    return None


def select_branch_decision_cause(result: InvestigationResult) -> dict[str, Any] | None:
    """Select a proven local choose/default decision when it directly precedes the effect.

    The implementation is intentionally conservative. It currently accepts only a
    runtime-proven ``default`` branch with one configured choice and one failed condition,
    plus a runtime path for the effect action that matches the investigated target. This
    is enough to distinguish a later local decision from an earlier technical trigger
    without turning configuration proximity into proof of execution.
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
        if str(choice) != "default":
            continue

        effect_action = _nearest_executed_branch_action(detail, result, action_index, choice)
        if not effect_action:
            continue
        command_path, config_action = effect_action

        failed = _single_failed_default_condition(detail, action_index)
        if not failed:
            continue
        condition_config, runtime, condition_path = failed
        condition = _condition_detail(condition_config, runtime)
        if not condition:
            continue

        delay_seconds = _previous_delay_seconds(detail, action_index)
        if delay_seconds is not None:
            condition["delay_seconds"] = delay_seconds

        domain, service = _action_semantics(config_action)
        return {
            "kind": "branch_decision",
            "origin": "choose_default",
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
    return None
