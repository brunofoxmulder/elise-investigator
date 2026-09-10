from __future__ import annotations

from typing import Any

from action_effect_cause import _executed_commands, _matches_effect
from causal_utils import nodes, trace_detail
from models import InvestigationResult
from trace_final_action_dev63 import _supported_true_condition


def _config_at_path(config: dict[str, Any], path: str) -> Any:
    """Resolve one HA trace path against config without searching unrelated branches."""
    current: Any = config
    parts = [part for part in str(path).split("/") if part]
    index = 0
    while index < len(parts):
        token = parts[index]
        if token == "action":
            actions = current.get("actions") if isinstance(current, dict) else None
            if not isinstance(actions, list) or index + 1 >= len(parts):
                return None
            try:
                current = actions[int(parts[index + 1])]
            except (ValueError, IndexError):
                return None
            index += 2
            continue
        if token == "choose":
            choices = current.get("choose") if isinstance(current, dict) else None
            if not isinstance(choices, list) or index + 1 >= len(parts):
                return None
            try:
                current = choices[int(parts[index + 1])]
            except (ValueError, IndexError):
                return None
            index += 2
            continue
        if token == "sequence":
            sequence = current.get("sequence") if isinstance(current, dict) else None
            if not isinstance(sequence, list) or index + 1 >= len(parts):
                return None
            try:
                current = sequence[int(parts[index + 1])]
            except (ValueError, IndexError):
                return None
            index += 2
            continue
        if token == "conditions":
            conditions = current.get("conditions") if isinstance(current, dict) else None
            if isinstance(conditions, dict):
                conditions = [conditions]
            if not isinstance(conditions, list) or index + 1 >= len(parts):
                return None
            try:
                current = conditions[int(parts[index + 1])]
            except (ValueError, IndexError):
                return None
            index += 2
            continue
        return None
    return current


def _runtime_true(detail: dict[str, Any], path: str) -> dict[str, Any] | None:
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None
    for node in reversed(nodes(trace.get(path))):
        result = node.get("result")
        if isinstance(result, dict) and result.get("result") is True:
            runtime = dict(result)
            variables = runtime.get("variables")
            if isinstance(variables, dict) and runtime.get("state") is None:
                runtime.update({key: value for key, value in variables.items() if key not in runtime})
            return runtime
    return None


def select_executed_branch_conditions(result: InvestigationResult) -> dict[str, Any] | None:
    """Read proven conditions on the exact executed branch leading to the target action.

    Bounded/fail-closed: exactly one matching target command; only conditions inside
    choose branches structurally containing that command; maximum four conditions;
    every ancestor branch condition must be supported and runtime true. No temporal
    correlation and no scan of unrelated automations/entities.
    """
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None

    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None
    config = detail.get("config")
    trace = detail.get("trace")
    if not isinstance(config, dict) or not isinstance(trace, dict):
        return None

    matches = [
        command
        for command in _executed_commands(detail, result.entity_id)
        if _matches_effect(command, result)
    ]
    if len(matches) != 1:
        return None
    command_path = str(matches[0].get("path") or "")
    if not command_path:
        return None

    ancestor_paths: list[str] = []
    for raw_path in trace:
        path = str(raw_path)
        marker = "/conditions/"
        if marker not in path:
            continue
        branch_prefix, _, suffix = path.rpartition(marker)
        if not suffix.isdigit():
            continue
        if command_path.startswith(branch_prefix + "/"):
            ancestor_paths.append(path)

    if not 1 <= len(ancestor_paths) <= 4:
        return None

    conditions: list[dict[str, Any]] = []
    for path in sorted(set(ancestor_paths)):
        config_condition = _config_at_path(config, path)
        runtime = _runtime_true(detail, path)
        if not isinstance(config_condition, dict) or not isinstance(runtime, dict):
            return None
        item = _supported_true_condition(config_condition, runtime)
        if not item:
            return None
        item["path"] = path
        conditions.append(item)

    if not 1 <= len(conditions) <= 4:
        return None

    return {
        "kind": "branch_decision",
        "origin": "executed_branch_conditions",
        "path": "executed-branch",
        "command_path": command_path,
        "proven": True,
        "detail": {"conditions": conditions},
        "effect_command": {
            "path": command_path,
            "domain": matches[0].get("domain"),
            "service": matches[0].get("service"),
        },
    }
