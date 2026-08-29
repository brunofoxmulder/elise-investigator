from __future__ import annotations

from typing import Any

from causal_factors import structured_factor
from causal_utils import nodes, walk_contains


def _one_entity(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
        return value[0]
    return None


def _predicate(config: dict[str, Any]) -> tuple[Any, ...] | None:
    platform = str(config.get("trigger") or config.get("condition") or "")
    entity_id = _one_entity(config.get("entity_id"))
    if platform not in {"state", "numeric_state"} or not entity_id:
        return None
    if platform == "state":
        expected = config.get("state") if config.get("state") is not None else config.get("to")
        if expected is None:
            return None
        return ("state", entity_id, str(expected))
    above = config.get("above")
    below = config.get("below")
    if above is None and below is None:
        return None
    return ("numeric_state", entity_id, above, below)


def _condition_runtime(trace: dict[str, Any], path: str) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for trace_path, raw in trace.items():
        text = str(trace_path)
        if text != path and not text.startswith(path + "/"):
            continue
        for node in nodes(raw):
            result = node.get("result")
            if isinstance(result, dict):
                candidates.append(result)
    for result in reversed(candidates):
        if result.get("result") is True or result.get("condition_result") is True:
            return result
    return None


def _factor(config: dict[str, Any], runtime: dict[str, Any], path: str) -> dict[str, Any] | None:
    pred = _predicate(config)
    if pred is None:
        return None
    platform = pred[0]
    entity_id = pred[1]
    if platform == "state":
        return structured_factor(
            kind="state",
            role="cause",
            proven=True,
            relation="is",
            value=pred[2],
            proof_entity_id=entity_id,
            proof_path=path,
            proof_runtime=runtime,
        )

    above, below = pred[2], pred[3]
    relation = None
    threshold = None
    if above is not None and below is None:
        relation, threshold = "above", above
    elif below is not None and above is None:
        relation, threshold = "below", below
    else:
        return None
    return structured_factor(
        kind="numeric_state",
        role="cause",
        proven=True,
        relation=relation,
        value=runtime.get("state"),
        threshold=threshold,
        proof_entity_id=entity_id,
        proof_path=path,
        proof_runtime=runtime,
    )


def combined_trigger_condition_factors(
    detail: dict[str, Any], target_entity_id: str
) -> list[dict[str, Any]]:
    """Return a proven conjunction only for repeated trigger predicates.

    A true condition is promoted to a functional cause only when the same predicate
    also exists as an automation trigger. This conservative rule fits automations
    that use several alternative triggers to re-evaluate one conjunction, while it
    avoids promoting ordinary guards (window closed, presence allowed, etc.) merely
    because they were true.

    Supported in dev.43: top-level state/numeric_state conditions and conditions of
    one executed top-level choose branch whose sequence references the target entity.
    Unsupported/nested/ambiguous shapes simply yield no combined cause.
    """
    if not isinstance(detail, dict) or not target_entity_id:
        return []
    config = detail.get("config")
    trace = detail.get("trace")
    if not isinstance(config, dict) or not isinstance(trace, dict):
        return []

    raw_triggers = config.get("triggers") if isinstance(config.get("triggers"), list) else config.get("trigger")
    if isinstance(raw_triggers, dict):
        raw_triggers = [raw_triggers]
    if not isinstance(raw_triggers, list):
        return []
    trigger_predicates = {
        pred for item in raw_triggers if isinstance(item, dict) if (pred := _predicate(item)) is not None
    }
    if len(trigger_predicates) < 2:
        return []

    candidates: list[tuple[dict[str, Any], dict[str, Any], str]] = []

    raw_conditions = config.get("conditions") if isinstance(config.get("conditions"), list) else config.get("condition")
    if isinstance(raw_conditions, dict):
        raw_conditions = [raw_conditions]
    for index, condition in enumerate(raw_conditions or []):
        if not isinstance(condition, dict) or _predicate(condition) not in trigger_predicates:
            continue
        path = f"condition/{index}"
        runtime = _condition_runtime(trace, path)
        if runtime is not None:
            candidates.append((condition, runtime, path))

    raw_actions = config.get("actions") if isinstance(config.get("actions"), list) else config.get("action")
    if isinstance(raw_actions, dict):
        raw_actions = [raw_actions]
    for action_index, action in enumerate(raw_actions or []):
        if not isinstance(action, dict):
            continue
        choices = action.get("choose")
        if not isinstance(choices, list):
            continue
        for choice_index, choice in enumerate(choices):
            if not isinstance(choice, dict) or not walk_contains(choice.get("sequence"), target_entity_id):
                continue
            conditions = choice.get("conditions")
            if isinstance(conditions, dict):
                conditions = [conditions]
            if not isinstance(conditions, list):
                continue
            for condition_index, condition in enumerate(conditions):
                if not isinstance(condition, dict) or _predicate(condition) not in trigger_predicates:
                    continue
                path = f"action/{action_index}/choose/{choice_index}/conditions/{condition_index}"
                runtime = _condition_runtime(trace, path)
                if runtime is not None:
                    candidates.append((condition, runtime, path))

    factors: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for condition, runtime, path in candidates:
        pred = _predicate(condition)
        if pred is None or pred in seen:
            continue
        factor = _factor(condition, runtime, path)
        if factor is None:
            continue
        seen.add(pred)
        factors.append(factor)

    return factors if len(factors) >= 2 else []
