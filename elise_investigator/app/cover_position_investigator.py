from __future__ import annotations

from dataclasses import replace
from typing import Any

from investigator import _dt, _history_time
from main_dev30 import EffectiveTransitionInvestigator
from models import InvestigationRequest, InvestigationResult
from proof_policy import StrictInvestigator, executed_trace_actions

_POSITION_ATTRIBUTE = "current_position"
_COVER_POSITION_EPISODE_MAX_SECONDS = 300
_STATUS_RANK = {"indeterminate": 0, "probable": 1, "confirmed": 2}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_number(left: Any, right: Any) -> bool:
    a = _number(left)
    b = _number(right)
    return a is not None and b is not None and abs(a - b) < 1e-9


def _position_from_action(action: dict[str, Any]) -> Any:
    data = action.get("data")
    return data.get("position") if isinstance(data, dict) else None


def _matching_position_command_source(
    result: InvestigationResult,
    entity_id: str,
    final_position: Any,
) -> str | None:
    """Return the unique trace source that executed the matching set_cover_position.

    Temporal proximity or a configuration mention is never enough. The command must
    be present in a retained runtime trace, target the investigated cover and request
    exactly the final position observed by Home Assistant.
    """

    sources: set[str] = set()
    for evidence in result.evidence:
        if evidence.kind != "trace" or not isinstance(evidence.raw, dict):
            continue
        for action in executed_trace_actions(evidence.raw, entity_id):
            if action.get("service") != "cover.set_cover_position":
                continue
            if not _same_number(_position_from_action(action), final_position):
                continue
            if evidence.source:
                sources.add(str(evidence.source))
    return next(iter(sources)) if len(sources) == 1 else None


class CoverPositionInvestigator(EffectiveTransitionInvestigator):
    """Attach partial cover positions to the proven start of the same movement.

    Home Assistant can finish a partial cover command with one update containing both
    ``closing -> open`` (or ``opening -> open``) and ``current_position: X -> Y``.
    Looking only at the terminal primary state loses the causal meaning of the partial
    target. Dev.32 keeps the position change as the observed effect, finds the adjacent
    coherent opening/closing episode, and accepts the anchor only when its runtime trace
    contains exactly the matching ``cover.set_cover_position`` command.
    """

    async def _anchor_investigate(self, request: InvestigationRequest) -> InvestigationResult:
        # Call the strict base engine directly. Dynamic dispatch still preserves the
        # dev.30 effective-transition selector, while avoiding recursive cover episode
        # post-processing for the synthetic movement-start request.
        return await StrictInvestigator.investigate(self, request)

    async def _cover_position_anchor(
        self,
        request: InvestigationRequest,
        result: InvestigationResult,
    ) -> tuple[dict[str, Any], InvestigationResult] | None:
        if not request.entity_id.startswith("cover."):
            return None
        if request.attribute != _POSITION_ATTRIBUTE:
            return None
        if result.event_type != "attribute_change":
            return None

        before_position = _number(result.observed.get("before"))
        after_position = _number(result.observed.get("after"))
        if before_position is None or after_position is None or before_position == after_position:
            return None
        direction = "opening" if after_position > before_position else "closing"

        terminal_time = _dt(result.event_time)
        window = result.meta.get("window") if isinstance(result.meta, dict) else None
        start = _dt(window.get("start")) if isinstance(window, dict) else None
        end = _dt(window.get("end")) if isinstance(window, dict) else None
        if terminal_time is None or start is None or end is None:
            return None

        history = await self.ha.get_history(request.entity_id, start, end, significant_only=False)
        timed: list[tuple[int, dict[str, Any], Any]] = []
        for index, row in enumerate(history):
            when = _history_time(row, attribute=_POSITION_ATTRIBUTE)
            if when is not None:
                timed.append((index, row, when))

        terminal_candidates = []
        for item in timed:
            attrs = item[1].get("attributes") if isinstance(item[1].get("attributes"), dict) else {}
            if _same_number(attrs.get(_POSITION_ATTRIBUTE), after_position):
                terminal_candidates.append(item)
        if not terminal_candidates:
            return None

        terminal_index, _, matched_terminal_time = min(
            terminal_candidates,
            key=lambda item: abs((item[2] - terminal_time).total_seconds()),
        )
        if abs((matched_terminal_time - terminal_time).total_seconds()) > 1.0:
            return None
        if terminal_index < 1:
            return None

        # The movement state must be directly adjacent to the final position update.
        # This prevents an unrelated older opening/closing state from being borrowed.
        motion_index = terminal_index - 1
        motion_row = history[motion_index]
        if str(motion_row.get("state") or "") != direction:
            return None

        # Walk backwards only through one contiguous movement block, so the causal
        # anchor is the beginning of this exact episode rather than its last refresh.
        while motion_index > 0:
            previous_row = history[motion_index - 1]
            if str(previous_row.get("state") or "") != direction:
                break
            previous_time = _history_time(previous_row)
            if previous_time is None:
                break
            if (matched_terminal_time - previous_time).total_seconds() > _COVER_POSITION_EPISODE_MAX_SECONDS:
                break
            motion_index -= 1

        motion_row = history[motion_index]
        motion_time = _history_time(motion_row)
        if motion_time is None:
            return None
        duration = (matched_terminal_time - motion_time).total_seconds()
        if duration < 0 or duration > _COVER_POSITION_EPISODE_MAX_SECONDS:
            return None

        anchor_request = replace(
            request,
            observed_time=motion_time.isoformat(),
            observed_value=direction,
            attribute=None,
        )
        anchor_result = await self._anchor_investigate(anchor_request)
        command_source = _matching_position_command_source(
            anchor_result,
            request.entity_id,
            after_position,
        )
        episode = {
            "recognized": True,
            "kind": "partial_position",
            "direction": direction,
            "before_position": before_position,
            "after_position": after_position,
            "motion_start_time": motion_time.isoformat(),
            "terminal_time": matched_terminal_time.isoformat(),
            "motion_duration_seconds": duration,
            "effect_command": "cover.set_cover_position",
            "effect_command_source": command_source,
            "effect_command_proven": command_source is not None,
            "rule": "adjacent_cover_motion_plus_matching_runtime_set_cover_position",
            "causal_anchor_status": anchor_result.status,
            "causal_anchor_event_time": anchor_result.event_time,
            "causal_anchor_used": False,
        }
        return episode, anchor_result

    async def _apply_cover_episode(
        self,
        request: InvestigationRequest,
        result: InvestigationResult,
    ) -> None:
        if request.entity_id.startswith("cover.") and request.attribute == _POSITION_ATTRIBUTE:
            resolved = await self._cover_position_anchor(request, result)
            if resolved is None:
                return
            episode, anchor_result = resolved
            result.meta["cover_position_episode"] = episode

            source = episode.get("effect_command_source")
            anchor_type = str(anchor_result.cause.get("type") or "unknown")
            anchor_source = anchor_result.cause.get("entity_id")
            if (
                not source
                or anchor_type not in {"automation", "script"}
                or anchor_result.cause.get("system_confirmed") is not True
                or str(anchor_source or "") != str(source)
                or _STATUS_RANK.get(anchor_result.status, 0) <= 0
            ):
                return

            if _STATUS_RANK.get(anchor_result.status, 0) >= _STATUS_RANK.get(result.status, 0):
                result.status = anchor_result.status
                result.cause = dict(anchor_result.cause)
                result.chain = list(anchor_result.chain)
                result.candidates = list(anchor_result.candidates)
                result.evidence.extend(anchor_result.evidence)
                result.limits = list(dict.fromkeys([*result.limits, *anchor_result.limits]))
                episode["causal_anchor_used"] = True
            return

        await super()._apply_cover_episode(request, result)
