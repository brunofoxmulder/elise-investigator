from __future__ import annotations

import re
from typing import Any

from models import InvestigationResult


def _node_passed(nodes: Any) -> bool:
    if not isinstance(nodes, list):
        nodes = [nodes]
    for node in nodes:
        if not isinstance(node, dict):
            continue
        result = node.get("result")
        if isinstance(result, dict) and result.get("result") is True:
            return True
        if result is True:
            return True
    return False


def _last_result(nodes: Any) -> dict[str, Any]:
    if not isinstance(nodes, list):
        nodes = [nodes]
    for node in reversed(nodes):
        if isinstance(node, dict) and isinstance(node.get("result"), dict):
            return node["result"]
    return {}


def _condition_configs(detail: dict[str, Any]) -> list[Any]:
    config = detail.get("config")
    if not isinstance(config, dict):
        return []
    value = config.get("condition")
    if value is None:
        value = config.get("conditions")
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _single_entity_id(config: dict[str, Any]) -> str | None:
    value = config.get("entity_id")
    if isinstance(value, str):
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
        return value[0]
    return None


def _condition_trace_detail(trace_nodes: dict[str, Any], index: int) -> dict[str, Any]:
    prefix = f"condition/{index}/"
    direct = trace_nodes.get(f"condition/{index}")
    merged: dict[str, Any] = {}
    if direct is not None:
        merged.update(_last_result(direct))
    for path, nodes in trace_nodes.items():
        if not str(path).startswith(prefix):
            continue
        result = _last_result(nodes)
        for key, value in result.items():
            if key not in merged or merged[key] is None:
                merged[key] = value
    return merged


def _supported_condition(
    config: Any,
    *,
    trace_detail: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    condition_type = str(config.get("condition") or "")
    entity_id = _single_entity_id(config)
    if not entity_id:
        return None

    if condition_type == "state":
        expected = config.get("state")
        if isinstance(expected, list):
            if len(expected) != 1:
                return None
            expected = expected[0]
        if expected is None:
            expected = trace_detail.get("wanted_state")
        actual = trace_detail.get("state")
        return {
            "kind": "condition",
            "condition_type": "state",
            "entity_id": entity_id,
            "actual": actual,
            "expected": expected,
            "proven": True,
        }

    if condition_type == "numeric_state":
        above = config.get("above")
        below = config.get("below")
        if above is None:
            above = trace_detail.get("wanted_state_above")
        if below is None:
            below = trace_detail.get("wanted_state_below")
        actual = trace_detail.get("state")
        if above is None and below is None:
            return None
        return {
            "kind": "condition",
            "condition_type": "numeric_state",
            "entity_id": entity_id,
            "actual": actual,
            "above": above,
            "below": below,
            "proven": True,
        }

    return None


def extract_passed_conditions(result: InvestigationResult) -> list[dict[str, Any]]:
    """Extract only conditions explicitly evaluated as true in the matched trace.

    Configuration provides semantics, never proof. Proof comes from the runtime
    ``condition/N`` trace node with ``result.result == true``.
    """
    if result.status != "confirmed":
        return []
    if result.cause.get("type") not in {"automation", "script"}:
        return []
    if result.cause.get("system_confirmed") is not True:
        return []

    source = result.cause.get("entity_id")
    trace_detail: dict[str, Any] | None = None
    for evidence in result.evidence:
        if evidence.kind != "trace" or not isinstance(evidence.raw, dict):
            continue
        if source and evidence.source and evidence.source != source:
            continue
        trace_detail = evidence.raw
        break
    if trace_detail is None:
        return []

    trace_nodes = trace_detail.get("trace")
    if not isinstance(trace_nodes, dict):
        return []
    configs = _condition_configs(trace_detail)
    if not configs:
        return []

    passed: list[dict[str, Any]] = []
    for path, nodes in trace_nodes.items():
        match = re.fullmatch(r"condition/(\d+)", str(path))
        if not match or not _node_passed(nodes):
            continue
        index = int(match.group(1))
        if index >= len(configs):
            continue
        item = _supported_condition(
            configs[index],
            trace_detail=_condition_trace_detail(trace_nodes, index),
        )
        if item is not None:
            passed.append(item)
    return passed
