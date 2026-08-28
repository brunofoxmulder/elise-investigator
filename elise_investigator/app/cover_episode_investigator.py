from __future__ import annotations

from dataclasses import replace
from typing import Any

from cover_position_investigator import CoverPositionInvestigator
from investigator import _dt, _history_time
from models import InvestigationRequest, InvestigationResult

_COVER_EPISODE_MAX_SECONDS = 300
_TERMINAL_SPECS: dict[str, dict[str, str]] = {
    "closed": {"motion": "closing", "origin": "open", "direction": "closing"},
    "open": {"motion": "opening", "origin": "closed", "direction": "opening"},
}
_ALLOWED_CONTEXT_SERVICES = {"open_cover", "close_cover", "set_cover_position"}


def _cover_context_service(result: InvestigationResult) -> str | None:
    """Return a proven cover service marker from retained Logbook evidence.

    ``context_service`` proves which Home Assistant service was involved in the
    movement, but it does not prove who or what invoked it. Dev.33 therefore keeps
    it as episode evidence only and never upgrades causal certainty from it alone.
    """

    for evidence in result.evidence:
        if evidence.kind != "logbook" or not isinstance(evidence.raw, dict):
            continue
        service = str(evidence.raw.get("context_service") or "").strip()
        domain = str(evidence.raw.get("context_domain") or "").strip()
        if service not in _ALLOWED_CONTEXT_SERVICES:
            continue
        if domain and domain != "cover":
            continue
        return f"cover.{service}"
    return None


class CoverEpisodeInvestigator(CoverPositionInvestigator):
    """Use the beginning of one contiguous cover motion as causal anchor.

    Home Assistant can persist several ``opening`` or ``closing`` history rows while
    a shutter physically moves. The older terminal-episode policy expected exactly
    three adjacent rows (origin -> motion -> terminal) and therefore rejected a
    perfectly coherent sequence such as ``closed -> opening -> opening -> open``.

    Dev.33 walks backward through the contiguous motion block and still requires the
    correct origin state immediately before that block. Temporal proximity alone is
    never enough.
    """

    async def _cover_episode_anchor(
        self,
        request: InvestigationRequest,
        result: InvestigationResult,
    ) -> tuple[dict[str, Any], InvestigationResult] | None:
        if not request.entity_id.startswith("cover.") or request.attribute:
            return None

        terminal_state = str(result.observed.get("after") or "")
        spec = _TERMINAL_SPECS.get(terminal_state)
        if spec is None or result.event_type != "state_change":
            return None

        terminal_time = _dt(result.event_time)
        window = result.meta.get("window") if isinstance(result.meta, dict) else None
        start = _dt(window.get("start")) if isinstance(window, dict) else None
        end = _dt(window.get("end")) if isinstance(window, dict) else None
        if terminal_time is None or start is None or end is None:
            return None

        history = await self.ha.get_history(
            request.entity_id,
            start,
            end,
            significant_only=False,
        )
        timed: list[tuple[int, dict[str, Any], Any]] = []
        for index, row in enumerate(history):
            when = _history_time(row)
            if when is not None:
                timed.append((index, row, when))

        terminal_candidates = [
            item for item in timed if str(item[1].get("state") or "") == terminal_state
        ]
        if not terminal_candidates:
            return None

        terminal_index, _, matched_terminal_time = min(
            terminal_candidates,
            key=lambda item: abs((item[2] - terminal_time).total_seconds()),
        )
        if abs((matched_terminal_time - terminal_time).total_seconds()) > 1.0:
            return None
        if terminal_index < 2:
            return None

        motion_index = terminal_index - 1
        if str(history[motion_index].get("state") or "") != spec["motion"]:
            return None

        # Walk to the first row of this exact movement. Repeated opening/closing
        # rows are normal while current_position is refreshed during travel.
        while motion_index > 0:
            previous_row = history[motion_index - 1]
            if str(previous_row.get("state") or "") != spec["motion"]:
                break
            previous_time = _history_time(previous_row)
            if previous_time is None:
                break
            if (
                matched_terminal_time - previous_time
            ).total_seconds() > _COVER_EPISODE_MAX_SECONDS:
                break
            motion_index -= 1

        origin_index = motion_index - 1
        if origin_index < 0:
            return None
        origin_row = history[origin_index]
        if str(origin_row.get("state") or "") != spec["origin"]:
            return None

        motion_row = history[motion_index]
        motion_time = _history_time(motion_row)
        origin_time = _history_time(origin_row)
        if motion_time is None:
            return None
        duration = (matched_terminal_time - motion_time).total_seconds()
        if duration < 0 or duration > _COVER_EPISODE_MAX_SECONDS:
            return None

        anchor_request = replace(
            request,
            observed_time=motion_time.isoformat(),
            observed_value=spec["motion"],
            attribute=None,
        )
        anchor_result = await self._anchor_investigate(anchor_request)
        context_service = _cover_context_service(anchor_result)

        episode = {
            "recognized": True,
            "kind": "terminal_state",
            "direction": spec["direction"],
            "origin_state": spec["origin"],
            "motion_state": spec["motion"],
            "terminal_state": terminal_state,
            "origin_time": origin_time.isoformat() if origin_time else None,
            "motion_start_time": motion_time.isoformat(),
            "terminal_time": matched_terminal_time.isoformat(),
            "motion_duration_seconds": duration,
            "context_service": context_service,
            "context_service_proves_invoker": False,
            "rule": "contiguous_cover_motion_block_with_exact_origin",
            "causal_anchor_status": anchor_result.status,
            "causal_anchor_event_time": anchor_result.event_time,
            "causal_anchor_used": False,
        }
        return episode, anchor_result
