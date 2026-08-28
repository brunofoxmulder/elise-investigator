from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from causal_utils import nodes, normalize_text, trace_detail, walk_contains
from models import InvestigationResult

_ENTITY_REF = re.compile(r"(?:states|state_attr)\(\s*['\"]([^'\"]+)['\"]")
_WORD = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


@dataclass(slots=True)
class RuntimeDecision:
    command_path: str
    output_variable: str
    target_value: Any
    factors: list[dict[str, Any]]
    reason: str | None


def _same_value(actual: Any, expected: Any) -> bool:
    if actual is None or expected is None:
        return False
    if str(actual) == str(expected):
        return True
    try:
        return abs(float(actual) - float(expected)) < 1e-9
    except (TypeError, ValueError):
        return False


def _config_variables(detail: dict[str, Any]) -> dict[str, Any]:
    config = detail.get("config")
    if not isinstance(config, dict):
        return {}
    value = config.get("variables")
    return value if isinstance(value, dict) else {}


def _expression(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def _dependencies(config_vars: dict[str, Any]) -> dict[str, set[str]]:
    names = set(config_vars)
    out: dict[str, set[str]] = {}
    for name, expression in config_vars.items():
        words = set(_WORD.findall(_expression(expression)))
        out[name] = (words & names) - {name}
    return out


def _source_entities(config_vars: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, expression in config_vars.items():
        refs = list(dict.fromkeys(_ENTITY_REF.findall(_expression(expression))))
        if refs:
            out[name] = refs
    return out


def _runtime_values(detail: dict[str, Any], names: set[str]) -> dict[str, Any]:
    values: dict[str, Any] = {}

    def take(mapping: Any) -> None:
        if not isinstance(mapping, dict):
            return
        for key, value in mapping.items():
            if key in names and isinstance(value, (str, int, float, bool)):
                values[key] = value

    take(detail.get("variables"))
    trace = detail.get("trace")
    if isinstance(trace, dict):
        for raw_nodes in trace.values():
            for node in nodes(raw_nodes):
                take(node.get("changed_variables"))
                take(node.get("variables"))
                result = node.get("result")
                if isinstance(result, dict):
                    take(result.get("variables"))
    return values


def _command_target_key(result: InvestigationResult) -> str | None:
    if result.observed.get("attribute") in {"current_position", "position"}:
        return "position"
    if result.observed.get("attribute") == "brightness":
        return "brightness"
    if result.observed.get("attribute") in {"temperature", "target_temp_high", "target_temp_low"}:
        return "temperature"
    domain = result.entity_id.split(".", 1)[0]
    if domain == "cover" and isinstance(result.observed.get("after"), (int, float)):
        return "position"
    return None


def _matching_command(result: InvestigationResult, detail: dict[str, Any]) -> tuple[str, str, Any] | None:
    target_key = _command_target_key(result)
    if not target_key:
        return None
    expected = result.observed.get("after")
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return None

    candidates: list[tuple[str, str, Any]] = []
    for path, raw_nodes in trace.items():
        path_text = str(path)
        if not path_text.startswith("action/"):
            continue
        for node in nodes(raw_nodes):
            runtime = node.get("result")
            params = runtime.get("params") if isinstance(runtime, dict) else None
            if not isinstance(params, dict) or not walk_contains(params.get("target"), result.entity_id):
                continue
            data = params.get("service_data") or params.get("data")
            if not isinstance(data, dict) or target_key not in data:
                continue
            if _same_value(data.get(target_key), expected):
                candidates.append((path_text, target_key, data.get(target_key)))
                break
    if len(candidates) != 1:
        return None
    return candidates[0]


def _depth(name: str, deps: dict[str, set[str]], seen: set[str] | None = None) -> int:
    seen = set(seen or ())
    if name in seen:
        return 0
    seen.add(name)
    children = deps.get(name) or set()
    return 1 + max((_depth(child, deps, seen) for child in children), default=0)


def _factor_category(variable: str, entity_id: str) -> str | None:
    text = normalize_text(f"{variable} {entity_id}")
    if any(token in text for token in ("azimut", "azimuth", "elevation", "solar", "sun_")):
        return "sun_position"
    if any(token in text for token in ("lux", "illumin", "luminos")):
        return "illuminance"
    if any(token in text for token in ("temperature", "temp_", "temperature_")):
        return "temperature"
    if any(token in text for token in ("current_position", "position_actuelle")):
        return "current_position"
    return None


def _reason_for_categories(categories: list[str]) -> str | None:
    unique = list(dict.fromkeys(categories))
    labels = {
        "sun_position": "la position du soleil",
        "illuminance": "la luminosité",
        "temperature": "la température",
        "current_position": "la position précédente",
    }
    readable = [labels[item] for item in unique if item in labels]
    if not readable:
        return None
    if len(readable) == 1:
        joined = readable[0]
    else:
        joined = ", ".join(readable[:-1]) + " et " + readable[-1]
    return f"le calcul automatique de cette valeur tenait compte de {joined}"


def extract_runtime_decision(result: InvestigationResult) -> RuntimeDecision | None:
    """Extract bounded runtime inputs of a rendered service target.

    This is deliberately weaker than claiming that every input was a decisive
    threshold. It proves only that the executed target value came from a runtime
    variable whose configured expression directly depended on the listed input
    variables. Direct external inputs are preferred over transitive dependencies.
    """
    if result.status != "confirmed":
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    if result.cause.get("system_confirmed") is not True:
        return None
    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None

    command = _matching_command(result, detail)
    if command is None:
        return None
    command_path, _, target_value = command

    config_vars = _config_variables(detail)
    if not config_vars:
        return None
    deps = _dependencies(config_vars)
    sources = _source_entities(config_vars)
    runtime = _runtime_values(detail, set(config_vars))

    matching_vars = [name for name, value in runtime.items() if _same_value(value, target_value)]
    if not matching_vars:
        return None
    # Prefer the most downstream variable when several happen to share the same value.
    matching_vars.sort(key=lambda name: (_depth(name, deps), len(deps.get(name, ()))), reverse=True)
    output = matching_vars[0]

    direct = [name for name in deps.get(output, set()) if name in sources]
    chosen: list[str] = list(dict.fromkeys(direct))
    if not chosen:
        queue = list(deps.get(output, set()))
        seen: set[str] = set()
        while queue:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            if name in sources:
                chosen.append(name)
                continue
            queue.extend(sorted(deps.get(name, set())))

    factors: list[dict[str, Any]] = []
    categories: list[str] = []
    for name in chosen:
        value = runtime.get(name)
        for entity_id in sources.get(name, []):
            category = _factor_category(name, entity_id)
            factor = {
                "role": "decision_input",
                "proven": True,
                "variable": name,
                "entity_id": entity_id,
            }
            if value is not None:
                factor["value"] = value
            if category:
                factor["category"] = category
                categories.append(category)
            factors.append(factor)

    if not factors:
        return None
    return RuntimeDecision(
        command_path=command_path,
        output_variable=output,
        target_value=target_value,
        factors=factors,
        reason=_reason_for_categories(categories),
    )
