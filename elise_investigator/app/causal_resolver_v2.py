from __future__ import annotations

import re
from typing import Any

from action_effect_cause import _executed_commands
from combined_trigger_condition_factors import combined_trigger_condition_factors
from human_cause import _proven_start_trigger
from models import InvestigationResult
from trace_action_local_dev68 import (
    select_completed_wait_cause,
    select_elapsed_delay_cause,
    select_trigger_with_true_conditions,
)
from trace_action_local_dev71 import select_adjacent_temporal_cause
from trace_final_action_dev63 import select_wait_timeout_cause

_TOP = re.compile(r"^action/(\d+)(?:/|$)")
_CHOOSE_SEQ = re.compile(r"^action/(\d+)/choose/(\d+)/sequence/(\d+)(?:/|$)")
_DEFAULT_SEQ = re.compile(r"^action/(\d+)/default/(\d+)(?:/|$)")
_TEMPORAL_KEYS = ("delay", "wait_for_trigger", "wait_template")


def _trace_detail(result: InvestigationResult) -> dict[str, Any] | None:
    for evidence in result.evidence:
        if evidence.kind == "trace" and isinstance(evidence.raw, dict):
            return evidence.raw
    return None


def _same_value(actual: Any, expected: Any) -> bool:
    if actual is None or expected is None:
        return False
    if str(actual) == str(expected):
        return True
    try:
        return abs(float(actual) - float(expected)) < 1e-9
    except (TypeError, ValueError):
        return False


def _matches_effect_v2(command: dict[str, Any], result: InvestigationResult) -> bool:
    """Match one executed command to the observed effect, including cover positions."""
    domain = result.entity_id.split(".", 1)[0]
    if command.get("domain") != domain:
        return False
    service = str(command.get("service") or "")
    after = result.observed.get("after")
    after_text = str(after).casefold() if after is not None else ""

    if domain in {"light", "switch", "fan", "input_boolean"}:
        return (after_text == "off" and service == "turn_off") or (
            after_text == "on" and service == "turn_on"
        )

    if domain == "cover":
        if service == "close_cover":
            return after_text == "closed"
        if service == "open_cover":
            return after_text == "open"
        if service == "set_cover_position":
            data = command.get("data")
            position = data.get("position") if isinstance(data, dict) else None
            if result.observed.get("attribute") == "current_position":
                return _same_value(position, after)
            try:
                numeric = float(position)
            except (TypeError, ValueError):
                return False
            if after_text == "closed":
                return abs(numeric) < 1e-9
            if after_text == "open":
                return numeric > 0
        return False

    if domain == "lock":
        return (after_text == "locked" and service == "lock") or (
            after_text == "unlocked" and service == "unlock")
    return False


def unique_effect_command(result: InvestigationResult) -> dict[str, Any] | None:
    """Return the unique executed command that matches the observed target effect."""
    detail = _trace_detail(result)
    if not isinstance(detail, dict):
        return None
    matches = [
        command
        for command in _executed_commands(detail, result.entity_id)
        if _matches_effect_v2(command, result)
    ]
    return matches[0] if len(matches) == 1 else None


def _executed(trace: dict[str, Any], path: str) -> bool:
    value = trace.get(path)
    if isinstance(value, list):
        return bool(value)
    return isinstance(value, dict) and bool(value)


def _top_actions(config: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("actions", "action", "sequence"):
        raw = config.get(key)
        if isinstance(raw, list):
            return [item if isinstance(item, dict) else {} for item in raw]
    return []


def _is_temporal(action: dict[str, Any]) -> bool:
    return any(key in action for key in _TEMPORAL_KEYS)


def has_temporal_barrier_before_effect(
    result: InvestigationResult,
    command_path: str,
) -> bool:
    """Return True only for an executed temporal barrier before the target command."""
    detail = _trace_detail(result)
    if not isinstance(detail, dict):
        return False
    config = detail.get("config")
    trace = detail.get("trace")
    if not isinstance(config, dict) or not isinstance(trace, dict):
        return False

    top_match = _TOP.match(command_path)
    if not top_match:
        return False
    target_top = int(top_match.group(1))
    actions = _top_actions(config)

    for index in range(min(target_top, len(actions))):
        action = actions[index]
        if _is_temporal(action) and _executed(trace, f"action/{index}"):
            return True

    chosen = _CHOOSE_SEQ.match(command_path)
    if chosen:
        action_index, choice_index, target_seq = map(int, chosen.groups())
        if 0 <= action_index < len(actions):
            choices = actions[action_index].get("choose")
            if isinstance(choices, list) and 0 <= choice_index < len(choices):
                choice = choices[choice_index]
                sequence = choice.get("sequence") if isinstance(choice, dict) else None
                if isinstance(sequence, list):
                    for seq_index in range(min(target_seq, len(sequence))):
                        item = sequence[seq_index]
                        path = f"action/{action_index}/choose/{choice_index}/sequence/{seq_index}"
                        if isinstance(item, dict) and _is_temporal(item) and _executed(trace, path):
                            return True

    default = _DEFAULT_SEQ.match(command_path)
    if default:
        action_index, target_seq = map(int, default.groups())
        if 0 <= action_index < len(actions):
            sequence = actions[action_index].get("default")
            if isinstance(sequence, list):
                for seq_index in range(min(target_seq, len(sequence))):
                    item = sequence[seq_index]
                    path = f"action/{action_index}/default/{seq_index}"
                    if isinstance(item, dict) and _is_temporal(item) and _executed(trace, path):
                        return True

    return False


def _has_numeric_condition(candidate: dict[str, Any] | None) -> bool:
    if not isinstance(candidate, dict):
        return False
    detail = candidate.get("detail")
    conditions = detail.get("conditions") if isinstance(detail, dict) else None
    if not isinstance(conditions, list):
        return False
    return any(
        isinstance(item, dict)
        and str(item.get("platform") or item.get("condition") or "").casefold() == "numeric_state"
        for item in conditions
    )


def _start_trigger_cause(result: InvestigationResult) -> dict[str, Any] | None:
    trigger = _proven_start_trigger(result)
    if not isinstance(trigger, dict) or not trigger:
        return None
    return {
        "kind": "automation_trigger",
        "origin": "automation_trigger",
        "path": "trigger",
        "proven": True,
        "detail": dict(trigger),
    }


def _factor_conjunction(
    result: InvestigationResult,
    command_path: str,
) -> dict[str, Any] | None:
    detail = _trace_detail(result)
    if not isinstance(detail, dict):
        return None
    factors = combined_trigger_condition_factors(detail, result.entity_id)
    if len(factors) < 2:
        return None
    return {
        "kind": "required_factors",
        "origin": "proven_factor_conjunction",
        "path": "runtime-proven-repeated-trigger-factors",
        "command_path": command_path,
        "proven": True,
        "detail": {"factors": factors},
    }


def _local_release(result: InvestigationResult) -> dict[str, Any] | None:
    for selector in (
        select_completed_wait_cause,
        select_wait_timeout_cause,
        select_elapsed_delay_cause,
        select_adjacent_temporal_cause,
    ):
        candidate = selector(result)
        if isinstance(candidate, dict):
            return candidate
    return None


def resolve_cause(result: InvestigationResult) -> dict[str, Any] | None:
    """Choose one semantic cause object for the exact observed target action.

    The object may be a proven conjunction or a short causal sequence, but the resolver
    remains the single place where causal semantics are selected. Readers provide facts;
    the renderer only verbalizes the selected object.
    """
    if result.status != "confirmed" or result.cause.get("system_confirmed") is not True:
        return None
    if result.cause.get("type") not in {"automation", "script"}:
        return None

    command = unique_effect_command(result)
    if not isinstance(command, dict):
        return None
    command_path = str(command.get("path") or "")
    if not command_path:
        return None

    # A repeated-trigger conjunction is stronger than an ordinary true guard: every
    # promoted factor must itself exist as a configured trigger and be runtime-proven.
    root_conjunction = _factor_conjunction(result, command_path)
    release = _local_release(result)
    if isinstance(root_conjunction, dict) and isinstance(release, dict):
        return {
            "kind": "causal_sequence",
            "origin": "causal_sequence",
            "path": root_conjunction.get("path"),
            "command_path": command_path,
            "proven": True,
            "detail": {
                "factors": root_conjunction.get("detail", {}).get("factors", []),
                "release": release,
            },
        }
    if isinstance(release, dict):
        return release
    if isinstance(root_conjunction, dict):
        return root_conjunction

    # Preserve already validated threshold conjunctions for the simpler top-level shape.
    # Pure discrete state guards are evidence, not a human cause.
    combined = select_trigger_with_true_conditions(result)
    trigger = _proven_start_trigger(result)
    platform = str((trigger or {}).get("platform") or (trigger or {}).get("trigger") or "").casefold()
    if (
        isinstance(combined, dict)
        and platform in {"state", "numeric_state"}
        and _has_numeric_condition(combined)
    ):
        return combined

    # Only a barrier BEFORE this exact command can block fallback to the start trigger.
    # A later wait/delay is irrelevant to the earlier effect.
    if has_temporal_barrier_before_effect(result, command_path):
        return None

    return _start_trigger_cause(result)
