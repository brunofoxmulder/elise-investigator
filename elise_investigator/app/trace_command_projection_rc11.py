from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from causal_utils import trace_detail
from models import Evidence, InvestigationResult


_DEVICE_ACTION_SERVICES: dict[str, dict[str, str]] = {
    "cover": {
        "close": "close_cover",
        "open": "open_cover",
        "set_position": "set_cover_position",
    },
    "fan": {"turn_off": "turn_off", "turn_on": "turn_on"},
    "input_boolean": {"turn_off": "turn_off", "turn_on": "turn_on"},
    "light": {"turn_off": "turn_off", "turn_on": "turn_on"},
    "lock": {"lock": "lock", "unlock": "unlock"},
    "switch": {"turn_off": "turn_off", "turn_on": "turn_on"},
}


def _items(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [str(item) for item in values if isinstance(item, str) and item]


def _path_nodes(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [node for node in raw if isinstance(node, dict)]
    return [raw] if isinstance(raw, dict) else []


def _config_at_runtime_path(config: dict[str, Any], path: str) -> dict[str, Any] | None:
    """Resolve only the configuration node addressed by one executed HA path.

    The trace namespace is always ``action/<index>``. Raw automation traces store the
    root list under ``action``; normalized fixtures can use ``actions``. Nested tokens
    are followed literally, including the ``default`` branch emitted by HA.
    """
    parts = [part for part in str(path).split("/") if part]
    if len(parts) < 2 or parts[0] != "action":
        return None

    root = config.get("actions")
    if not isinstance(root, list):
        root = config.get("action")
    if not isinstance(root, list):
        root = config.get("sequence")
    try:
        current: Any = root[int(parts[1])]
    except (TypeError, ValueError, IndexError):
        return None

    index = 2
    while index < len(parts):
        token = parts[index]
        if token not in {"choose", "conditions", "default", "sequence"}:
            return None
        children = current.get(token) if isinstance(current, dict) else None
        if token == "conditions" and isinstance(children, dict):
            children = [children]
        if not isinstance(children, list) or index + 1 >= len(parts):
            return None
        try:
            current = children[int(parts[index + 1])]
        except (ValueError, IndexError):
            return None
        index += 2

    return current if isinstance(current, dict) else None


def _registry_matches_device_action(
    action: dict[str, Any],
    target_entity: str,
    registry: dict[str, Any] | None,
) -> bool:
    """Require the device action's entity reference and device to match the registry."""
    if not isinstance(registry, dict):
        return False
    if str(registry.get("entity_id") or "") != target_entity:
        return False

    registry_id = str(registry.get("id") or "")
    registry_device_id = str(registry.get("device_id") or "")
    action_entity_ref = str(action.get("entity_id") or "")
    action_device_id = str(action.get("device_id") or "")
    if not registry_id or not registry_device_id or not action_entity_ref or not action_device_id:
        return False
    if action_entity_ref not in {registry_id, target_entity}:
        return False
    if action_device_id != registry_device_id:
        return False
    return str(action.get("domain") or "") == target_entity.split(".", 1)[0]


def _runtime_params_for_target(
    params: dict[str, Any],
    target_entity: str,
    registry: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Keep runtime params only when their target identifies the exact entity.

    A device_id by itself is deliberately insufficient. An opaque entity-registry id is
    accepted only when the registry maps it to the observed entity; the copied target is
    then normalized for the existing resolver. The original trace remains untouched.
    """
    if not params.get("domain") or not params.get("service"):
        return None
    target = params.get("target")
    if not isinstance(target, dict):
        return None
    entity_refs = _items(target.get("entity_id"))
    if target_entity in entity_refs:
        return deepcopy(params)

    if not isinstance(registry, dict) or str(registry.get("entity_id") or "") != target_entity:
        return None
    registry_id = str(registry.get("id") or "")
    if not registry_id or registry_id not in entity_refs:
        return None

    device_refs = _items(target.get("device_id"))
    registry_device_id = str(registry.get("device_id") or "")
    if device_refs and (not registry_device_id or registry_device_id not in device_refs):
        return None

    normalized = deepcopy(params)
    normalized_target = dict(target)
    normalized_target["entity_id"] = target_entity
    normalized["target"] = normalized_target
    return normalized


def _service_command_from_config(
    action: dict[str, Any], target_entity: str
) -> dict[str, Any] | None:
    service_ref = action.get("action") or action.get("service")
    if not isinstance(service_ref, str) or service_ref.count(".") != 1:
        return None
    domain, service = service_ref.split(".", 1)
    if not domain or not service:
        return None

    target = action.get("target")
    target_refs = _items(target.get("entity_id")) if isinstance(target, dict) else []
    data = action.get("data")
    data_refs = _items(data.get("entity_id")) if isinstance(data, dict) else []
    if target_entity not in {*target_refs, *data_refs}:
        return None

    service_data = deepcopy(data) if isinstance(data, dict) else None
    return {
        "domain": domain,
        "service": service,
        "target": {"entity_id": target_entity},
        "service_data": service_data,
    }


def _device_command_from_config(
    action: dict[str, Any],
    target_entity: str,
    registry: dict[str, Any] | None,
) -> dict[str, Any] | None:
    domain = str(action.get("domain") or "")
    action_type = str(action.get("type") or "")
    service = _DEVICE_ACTION_SERVICES.get(domain, {}).get(action_type)
    if not service or not _registry_matches_device_action(action, target_entity, registry):
        return None

    service_data: dict[str, Any] | None = None
    if domain == "cover" and service == "set_cover_position" and action.get("position") is not None:
        service_data = {"position": deepcopy(action["position"])}
    return {
        "domain": domain,
        "service": service,
        "target": {"entity_id": target_entity},
        "service_data": service_data,
    }


def _config_command_for_target(
    action: dict[str, Any] | None,
    target_entity: str,
    registry: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(action, dict):
        return None
    service_command = _service_command_from_config(action, target_entity)
    if isinstance(service_command, dict):
        return service_command
    return _device_command_from_config(action, target_entity, registry)


def _project_detail(
    detail: dict[str, Any],
    target_entity: str,
    registry: dict[str, Any] | None,
) -> dict[str, Any]:
    projected = deepcopy(detail)
    config = projected.get("config")
    trace = projected.get("trace")
    if not isinstance(config, dict) or not isinstance(trace, dict):
        return projected

    for raw_path, raw_nodes in trace.items():
        path = str(raw_path)
        if not path.startswith("action/"):
            continue
        path_nodes = _path_nodes(raw_nodes)
        if not path_nodes:
            continue

        # Runtime parameters are authoritative for the whole executed path. When they
        # exist but do not identify the exact entity, fail closed and never consult
        # configuration as a second interpretation of the same execution.
        has_runtime_params = any(
            isinstance(node.get("result"), dict) and "params" in node["result"]
            for node in path_nodes
        )
        if has_runtime_params:
            for node in path_nodes:
                result_node = node.get("result")
                if not isinstance(result_node, dict) or "params" not in result_node:
                    continue
                params = result_node.get("params")
                exact = (
                    _runtime_params_for_target(params, target_entity, registry)
                    if isinstance(params, dict)
                    else None
                )
                result_node["params"] = exact if isinstance(exact, dict) else {}
            continue

        action = _config_at_runtime_path(config, path)
        command = _config_command_for_target(action, target_entity, registry)
        if not isinstance(command, dict):
            continue
        result_node = path_nodes[0].get("result")
        if not isinstance(result_node, dict):
            result_node = {}
            path_nodes[0]["result"] = result_node
        result_node["params"] = command

    return projected


def project_exact_effect_commands_rc11(
    result: InvestigationResult,
    registry: dict[str, Any] | None,
) -> InvestigationResult:
    """Project config-only commands into a copy consumed by the existing resolvers."""
    original_detail = trace_detail(result)
    if not isinstance(original_detail, dict):
        return result
    projected_detail = _project_detail(original_detail, result.entity_id, registry)

    replaced = False
    evidence: list[Evidence] = []
    for item in result.evidence:
        if not replaced and item.kind == "trace" and item.raw is original_detail:
            evidence.append(replace(item, raw=projected_detail))
            replaced = True
        else:
            evidence.append(item)
    return replace(result, evidence=evidence) if replaced else result

