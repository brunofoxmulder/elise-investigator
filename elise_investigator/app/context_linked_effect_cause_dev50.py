from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from action_effect_cause import _completed_wait_trigger, _merge_trigger, _select_wait_config
from causal_utils import nodes, trace_detail
from models import InvestigationResult

_TOP_LEVEL = re.compile(r"^action/(\d+)$")
_CHOOSE_SEQ = re.compile(r"^action/(\d+)/choose/(\d+)/sequence/(\d+)$")
_DEFAULT_SEQ = re.compile(r"^action/(\d+)/default/(\d+)$")
_EVENT_GRACE_SECONDS = 5.0


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _config_actions(detail: dict[str, Any]) -> list[dict[str, Any]]:
    config = detail.get("config")
    if not isinstance(config, dict):
        return []
    for key in ("actions", "action", "sequence"):
        actions = config.get(key)
        if isinstance(actions, list):
            return [item if isinstance(item, dict) else {} for item in actions]
    return []


def _configured_action(detail: dict[str, Any], path: str) -> dict[str, Any] | None:
    actions = _config_actions(detail)
    top = _TOP_LEVEL.fullmatch(path)
    if top:
        idx = int(top.group(1))
        return actions[idx] if 0 <= idx < len(actions) else None

    chosen = _CHOOSE_SEQ.fullmatch(path)
    if chosen:
        action_idx, choice_idx, seq_idx = map(int, chosen.groups())
        if not 0 <= action_idx < len(actions):
            return None
        choices = actions[action_idx].get("choose")
        if not isinstance(choices, list) or not 0 <= choice_idx < len(choices):
            return None
        choice = choices[choice_idx]
        sequence = choice.get("sequence") if isinstance(choice, dict) else None
        if isinstance(sequence, list) and 0 <= seq_idx < len(sequence):
            item = sequence[seq_idx]
            return item if isinstance(item, dict) else None
        return None

    default = _DEFAULT_SEQ.fullmatch(path)
    if default:
        action_idx, seq_idx = map(int, default.groups())
        if not 0 <= action_idx < len(actions):
            return None
        sequence = actions[action_idx].get("default")
        if isinstance(sequence, list) and 0 <= seq_idx < len(sequence):
            item = sequence[seq_idx]
            return item if isinstance(item, dict) else None
    return None


def _action_semantics(config_action: dict[str, Any]) -> tuple[str, str]:
    domain = str(config_action.get("domain") or "")
    action = str(config_action.get("action") or config_action.get("service") or "")
    action_type = str(config_action.get("type") or "")
    if "." in action:
        action_domain, service = action.split(".", 1)
        return action_domain, service
    return domain, action_type or action


def _matches_effect_semantics(config_action: dict[str, Any], result: InvestigationResult) -> bool:
    domain, service = _action_semantics(config_action)
    target_domain = result.entity_id.split(".", 1)[0]
    if domain and domain != target_domain:
        return False
    after = str(result.observed.get("after") or "").casefold()
    if target_domain in {"light", "switch", "fan", "input_boolean"}:
        return (after == "off" and service == "turn_off") or (after == "on" and service == "turn_on")
    if target_domain == "lock":
        return (after == "locked" and service == "lock") or (after == "unlocked" and service == "unlock")
    return False


def _node_time(node: dict[str, Any]) -> datetime | None:
    return _dt(node.get("timestamp"))


def _effect_action_path(detail: dict[str, Any], result: InvestigationResult) -> str | None:
    trace = detail.get("trace")
    event_time = _dt(result.event_time)
    if not isinstance(trace, dict) or event_time is None:
        return None

    candidates: list[tuple[float, str]] = []
    for path, raw_nodes in trace.items():
        path_text = str(path)
        config_action = _configured_action(detail, path_text)
        if not isinstance(config_action, dict) or not _matches_effect_semantics(config_action, result):
            continue
        for node in nodes(raw_nodes):
            when = _node_time(node)
            if when is None or when > event_time:
                continue
            distance = (event_time - when).total_seconds()
            if distance <= _EVENT_GRACE_SECONDS:
                candidates.append((distance, path_text))

    candidates.sort(key=lambda item: item[0])
    if not candidates:
        return None
    if len(candidates) > 1 and abs(candidates[1][0] - candidates[0][0]) < 1e-9:
        return None
    return candidates[0][1]


def _previous_sibling(path: str) -> str | None:
    top = _TOP_LEVEL.fullmatch(path)
    if top:
        idx = int(top.group(1))
        return f"action/{idx - 1}" if idx > 0 else None
    chosen = _CHOOSE_SEQ.fullmatch(path)
    if chosen:
        action_idx, choice_idx, seq_idx = map(int, chosen.groups())
        if seq_idx <= 0:
            return None
        return f"action/{action_idx}/choose/{choice_idx}/sequence/{seq_idx - 1}"
    default = _DEFAULT_SEQ.fullmatch(path)
    if default:
        action_idx, seq_idx = map(int, default.groups())
        if seq_idx <= 0:
            return None
        return f"action/{action_idx}/default/{seq_idx - 1}"
    return None


def select_context_linked_effect_cause(result: InvestigationResult) -> dict[str, Any] | None:
    """Recover a local wait cause from an exact source trace already linked to the effect.

    This is intentionally narrower than generic causal search. It never handles covers,
    requires a confirmed automation/script source, requires a primary on/off effect,
    then accepts only one effect-semantic executed action within five seconds of the
    observed event and a completed wait_for_trigger immediately before it in the same
    executed sequence.
    """
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None
    if result.entity_id.startswith("cover.") or result.observed.get("attribute") is not None:
        return None
    pair = (
        str(result.observed.get("before") or "").casefold(),
        str(result.observed.get("after") or "").casefold(),
    )
    if pair not in {("off", "on"), ("on", "off")}:
        return None

    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None
    command_path = _effect_action_path(detail, result)
    if not command_path:
        return None
    wait_path = _previous_sibling(command_path)
    if not wait_path:
        return None
    wait_action = _configured_action(detail, wait_path)
    if not isinstance(wait_action, dict) or not isinstance(wait_action.get("wait_for_trigger"), list):
        return None
    trigger = _completed_wait_trigger(detail, wait_path)
    if not trigger:
        return None
    config = _select_wait_config(wait_action, trigger)
    return {
        "kind": "action_trigger",
        "origin": "wait_for_trigger",
        "path": wait_path,
        "command_path": command_path,
        "proven": True,
        "detail": _merge_trigger(trigger, config),
        "effect_command": {"path": command_path},
    }
