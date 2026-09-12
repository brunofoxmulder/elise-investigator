from __future__ import annotations

import re
from typing import Any

from causal_utils import nodes
from models import InvestigationResult

_COVER_CHOOSE_COMMAND = re.compile(
    r"^action/(\d+)/choose/(\d+)/sequence/(\d+)(?:/|$)"
)


def _trace_detail(result: InvestigationResult) -> dict[str, Any] | None:
    for evidence in result.evidence:
        if evidence.kind == "trace" and isinstance(evidence.raw, dict):
            return evidence.raw
    return None


def _config_actions(detail: dict[str, Any]) -> list[dict[str, Any]]:
    config = detail.get("config")
    if not isinstance(config, dict):
        return []
    for key in ("actions", "action", "sequence"):
        raw = config.get(key)
        if isinstance(raw, list):
            return [item if isinstance(item, dict) else {} for item in raw]
    return []


def _runtime_true_result(trace: dict[str, Any], prefix: str) -> dict[str, Any] | None:
    """Return the deepest runtime condition result proven true under ``prefix``."""
    matches: list[tuple[int, dict[str, Any]]] = []
    for path, raw_nodes in trace.items():
        path_text = str(path)
        if path_text != prefix and not path_text.startswith(prefix + "/"):
            continue
        for node in nodes(raw_nodes):
            runtime = node.get("result")
            if isinstance(runtime, dict) and runtime.get("result") is True:
                matches.append((path_text.count("/"), runtime))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _single_entity_id(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
        return value[0]
    return None


def _numeric_factor(
    condition: dict[str, Any],
    runtime: dict[str, Any],
    path: str,
) -> dict[str, Any] | None:
    """Return one runtime-proven numeric decision factor.

    Numeric factors are useful cover decision inputs (temperature, lux, solar azimuth /
    elevation, etc.). Discrete state guards are intentionally not promoted here.
    """
    if str(condition.get("condition") or "").casefold() != "numeric_state":
        return None
    entity_id = _single_entity_id(condition.get("entity_id"))
    if not entity_id:
        return None
    above = condition.get("above")
    below = condition.get("below")
    if above is None and below is None:
        return None

    actual = runtime.get("state")
    if actual is None:
        variables = runtime.get("variables")
        if isinstance(variables, dict):
            actual = variables.get("state")

    return {
        "platform": "numeric_state",
        "entity_id": entity_id,
        "attribute": condition.get("attribute"),
        "above": above,
        "below": below,
        "actual": actual,
        "condition_result": True,
        "path": path,
    }


def cover_branch_numeric_factors(
    result: InvestigationResult,
    command: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return numeric conditions of the exact executed branch leading to a cover command.

    Scope is deliberately strict:
    - investigated entity must be a cover;
    - exact executed command must be ``cover.set_cover_position``;
    - command path must identify one executed ``choose`` branch;
    - every returned condition must be runtime-proven true in that same branch;
    - state/boolean guards are ignored instead of being promoted to causes.

    No time correlation and no configuration-only inference is used.
    """
    if result.entity_id.split(".", 1)[0] != "cover":
        return []
    if str(command.get("domain") or "") != "cover":
        return []
    if str(command.get("service") or "") != "set_cover_position":
        return []

    command_path = str(command.get("path") or "")
    match = _COVER_CHOOSE_COMMAND.match(command_path)
    if not match:
        return []
    action_index, choice_index, _sequence_index = map(int, match.groups())

    detail = _trace_detail(result)
    if not isinstance(detail, dict):
        return []
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return []
    actions = _config_actions(detail)
    if not 0 <= action_index < len(actions):
        return []
    choices = actions[action_index].get("choose")
    if not isinstance(choices, list) or not 0 <= choice_index < len(choices):
        return []
    selected = choices[choice_index]
    if not isinstance(selected, dict):
        return []

    conditions = selected.get("conditions")
    if isinstance(conditions, dict):
        conditions = [conditions]
    if not isinstance(conditions, list) or not 1 <= len(conditions) <= 8:
        return []

    branch_path = f"action/{action_index}/choose/{choice_index}"
    branch_proven = any(
        isinstance(node.get("result"), dict) and node["result"].get("result") is True
        for node in nodes(trace.get(branch_path))
    )
    if not branch_proven:
        return []

    factors: list[dict[str, Any]] = []
    for index, condition in enumerate(conditions):
        if not isinstance(condition, dict):
            continue
        condition_path = f"{branch_path}/conditions/{index}"
        runtime = _runtime_true_result(trace, condition_path)
        if not isinstance(runtime, dict):
            continue
        factor = _numeric_factor(condition, runtime, condition_path)
        if factor:
            factors.append(factor)
    return factors


def periodic_position_decision(
    result: InvestigationResult,
    command: dict[str, Any],
    trigger: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Describe a proven periodic cover positioning decision without promoting guards.

    This is intentionally narrow: cover domain only, proven time_pattern trigger only,
    and an executed ``cover.set_cover_position`` command already selected by the V2
    resolver as the unique effect command. The requested position is action evidence.
    Runtime-proven numeric conditions from the exact executed branch are added as cover
    decision factors; discrete state guards remain evidence only.
    """
    if result.entity_id.split(".", 1)[0] != "cover":
        return None
    if not isinstance(trigger, dict):
        return None
    platform = str(trigger.get("platform") or trigger.get("trigger") or "").casefold()
    if platform != "time_pattern":
        return None
    if str(command.get("domain") or "") != "cover":
        return None
    if str(command.get("service") or "") != "set_cover_position":
        return None

    data = command.get("data")
    position = data.get("position") if isinstance(data, dict) else None
    try:
        numeric_position = float(position)
    except (TypeError, ValueError):
        return None
    if not 0 <= numeric_position <= 100:
        return None

    factors = cover_branch_numeric_factors(result, command)
    return {
        "kind": "cover_periodic_position",
        "origin": "cover_periodic_position",
        "path": "trigger+effect_command",
        "command_path": command.get("path"),
        "proven": True,
        "detail": {
            "trigger": dict(trigger),
            "requested_position": numeric_position,
            "decision_factors": factors,
        },
        "effect_command": {
            "path": command.get("path"),
            "domain": command.get("domain"),
            "service": command.get("service"),
        },
    }
