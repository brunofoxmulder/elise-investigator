from __future__ import annotations

from typing import Any

from action_effect_cause import _completed_wait_trigger, _executed_commands, _matches_effect, _merge_trigger, _select_wait_config
from causal_utils import duration_seconds, duration_text, nodes, trace_detail
from models import InvestigationResult
from trace_branch_path_dev70 import _config_at_path


def _unique_effect_command(result: InvestigationResult) -> dict[str, Any] | None:
    detail = trace_detail(result)
    if not isinstance(detail, dict):
        return None
    matches = [
        command
        for command in _executed_commands(detail, result.entity_id)
        if _matches_effect(command, result)
    ]
    return matches[0] if len(matches) == 1 else None


def _previous_sibling_path(path: str) -> str | None:
    parts = [part for part in str(path).split("/") if part]
    if not parts:
        return None
    try:
        index = int(parts[-1])
    except ValueError:
        return None
    if index <= 0:
        return None
    return "/".join(parts[:-1] + [str(index - 1)])


def select_adjacent_temporal_cause(result: InvestigationResult) -> dict[str, Any] | None:
    """Explain an exact target command released by an adjacent delay/wait at any nesting depth.

    This is deliberately structural: one unique executed target command, one immediately
    preceding sibling in the same HA action sequence, and proof that this sibling executed.
    It never falls back to elapsed-clock correlation.
    """
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None

    detail = trace_detail(result)
    command = _unique_effect_command(result)
    if not isinstance(detail, dict) or not isinstance(command, dict):
        return None
    config = detail.get("config")
    trace = detail.get("trace")
    if not isinstance(config, dict) or not isinstance(trace, dict):
        return None

    command_path = str(command.get("path") or "")
    previous_path = _previous_sibling_path(command_path)
    if not previous_path:
        return None
    previous = _config_at_path(config, previous_path)
    if not isinstance(previous, dict) or not nodes(trace.get(previous_path)):
        return None

    if "delay" in previous:
        seconds = duration_seconds(previous.get("delay"))
        if seconds is None or seconds <= 0:
            return None
        return {
            "kind": "action_trigger",
            "origin": "delay_elapsed",
            "path": previous_path,
            "command_path": command_path,
            "proven": True,
            "detail": {
                "platform": "delay_elapsed",
                "delay": previous.get("delay"),
                "delay_seconds": seconds,
                "duration_text": duration_text(seconds),
            },
            "effect_command": {
                "path": command_path,
                "domain": command.get("domain"),
                "service": command.get("service"),
            },
        }

    if isinstance(previous.get("wait_for_trigger"), list):
        actual = _completed_wait_trigger(detail, previous_path)
        if not actual:
            return None
        wait_config = _select_wait_config(previous, actual)
        return {
            "kind": "action_trigger",
            "origin": "wait_for_trigger",
            "path": previous_path,
            "command_path": command_path,
            "proven": True,
            "detail": _merge_trigger(actual, wait_config),
            "effect_command": {
                "path": command_path,
                "domain": command.get("domain"),
                "service": command.get("service"),
            },
        }

    return None
