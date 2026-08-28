from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from action_effect_cause import select_effect_linked_cause
from branch_decision_cause import select_branch_decision_cause
from condition_context import extract_passed_conditions
from human_cause import select_human_cause
from human_explanation import build_human_causal_answer
from investigator import _dt, _extract_trace_start, _history_time, _trace_run_id
from models import InvestigationRequest, InvestigationResult
from proof_policy import StrictInvestigator, VERSION as BASE_VERSION
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text, human_rule_text
from uncertainty_explanation import build_indeterminate_explanation

VERSION = "0.2.0-dev.16"
_ALLOWED_DETAIL_MODES = {"simple", "detailed"}
_ADAPTIVE_TARGETS = (60, 180)
_MISSING_EVENT_TYPES = {"current_state_only", "window_boundary_state"}
_TRACE_EVENT_GRACE_SECONDS = 300
_COVER_EPISODE_MAX_SECONDS = 300
_COVER_TERMINAL = {
    "closed": {"motion": "closing", "origin": "open", "direction": "closing"},
    "open": {"motion": "opening", "origin": "closed", "direction": "opening"},
}
_STATUS_RANK = {"indeterminate": 0, "probable": 1, "confirmed": 2}


def normalize_detail_mode(value: str | None) -> str:
    mode = str(value or "simple").strip().lower()
    return mode if mode in _ALLOWED_DETAIL_MODES else "simple"


def _extract_trace_finish(trace: dict[str, Any]) -> datetime | None:
    """Read the execution end timestamp from current and older HA trace shapes."""
    timestamp = trace.get("timestamp")
    if isinstance(timestamp, dict):
        for key in ("finish", "end", "stop"):
            finish = _dt(timestamp.get(key))
            if finish is not None:
                return finish
    for key in ("finish", "end", "stop"):
        finish = _dt(trace.get(key))
        if finish is not None:
            return finish
    return None


def _trace_distance_from_event(trace: dict[str, Any], event_time: datetime) -> float | None:
    """Distance from an event to an execution interval, not just its start."""
    start = _extract_trace_start(trace)
    if start is None:
        return None
    finish = _extract_trace_finish(trace)
    if finish is not None and finish >= start:
        if start <= event_time <= finish:
            return 0.0
        if event_time < start:
            return (start - event_time).total_seconds()
        return (event_time - finish).total_seconds()
    return abs((start - event_time).total_seconds())


class V02Investigator(StrictInvestigator):
    """Validated 0.2 causal layer reused by dev.29 journal enrichment.

    This preserves the dev.16 proof improvements: trace interval matching,
    effect-command matching, action-local wait/choose causes and coherent cover
    movement episodes. Dev.29 uses this class only for background enrichment;
    the manual dev.28 investigation endpoint remains on its existing engine.
    """

    async def _best_trace_for_source(
        self,
        source_entity_id: str,
        event_time: datetime | None,
    ) -> dict[str, Any] | None:
        resolved = await self._config_id_for_entity(source_entity_id)
        if not resolved:
            return None
        domain, item_id = resolved
        traces = await self.ha.list_traces(domain, item_id)
        if not traces:
            return None

        if event_time:
            timed: list[tuple[dict[str, Any], float]] = []
            for trace in traces:
                distance = _trace_distance_from_event(trace, event_time)
                if distance is not None:
                    timed.append((trace, distance))
            if timed:
                summary, distance = min(timed, key=lambda pair: pair[1])
                if distance > _TRACE_EVENT_GRACE_SECONDS:
                    return None
            else:
                summary = traces[-1]
        else:
            summary = traces[-1]

        run_id = _trace_run_id(summary)
        if not run_id:
            return None
        detail = await self.ha.get_trace(domain, item_id, run_id)
        if detail is None:
            return {
                "summary": summary,
                "detail": None,
                "expired": True,
                "domain": domain,
                "item_id": item_id,
            }
        return {
            "summary": summary,
            "detail": detail,
            "expired": False,
            "domain": domain,
            "item_id": item_id,
        }

    def _build_answer(self, result: InvestigationResult) -> str:
        human = build_human_causal_answer(result)
        if human:
            return human
        uncertainty = build_indeterminate_explanation(result)
        if uncertainty:
            return uncertainty
        return super()._build_answer(result)

    def _adaptive_windows(self) -> list[int]:
        start = max(5, min(int(self.default_window_minutes), 180))
        windows = [start]
        for candidate in _ADAPTIVE_TARGETS:
            if candidate > start and candidate not in windows:
                windows.append(candidate)
        return windows

    @staticmethod
    def _event_is_missing(result: InvestigationResult) -> bool:
        return result.event_type in _MISSING_EVENT_TYPES

    async def _investigate_with_adaptive_window(
        self,
        request: InvestigationRequest,
    ) -> InvestigationResult:
        if request.observed_time or request.window_minutes is not None:
            result = await super().investigate(request)
            result.meta["adaptive_window"] = {
                "enabled": False,
                "reason": "explicit_user_timing",
                "attempts": [],
                "selected_window_minutes": request.window_minutes or self.default_window_minutes,
                "expanded": False,
            }
            return result

        attempts: list[dict[str, Any]] = []
        result: InvestigationResult | None = None
        selected_window = self.default_window_minutes

        for window in self._adaptive_windows():
            attempt_request = replace(request, window_minutes=window)
            result = await super().investigate(attempt_request)
            selected_window = window
            missing_event = self._event_is_missing(result)
            attempts.append(
                {
                    "window_minutes": window,
                    "event_type": result.event_type,
                    "status": result.status,
                    "usable_event_found": not missing_event,
                }
            )
            if not missing_event:
                break

        assert result is not None
        result.meta["adaptive_window"] = {
            "enabled": True,
            "attempts": attempts,
            "selected_window_minutes": selected_window,
            "expanded": len(attempts) > 1,
            "usable_event_found": not self._event_is_missing(result),
            "max_window_minutes": self._adaptive_windows()[-1],
            "rule": "expand_only_when_event_missing",
        }
        return result

    async def _cover_episode_anchor(
        self,
        request: InvestigationRequest,
        result: InvestigationResult,
    ) -> tuple[dict[str, Any], InvestigationResult] | None:
        """Resolve one coherent cover terminal movement to its proven start state.

        Only an exact adjacent sequence open -> closing -> closed or
        closed -> opening -> open is accepted. Time proximity alone is never enough.
        The final open/closed event stays the observed effect; the beginning of the same
        episode is used only as the causal anchor.
        """
        if not request.entity_id.startswith("cover.") or request.attribute:
            return None
        terminal_state = str(result.observed.get("after") or "")
        spec = _COVER_TERMINAL.get(terminal_state)
        if spec is None or result.event_type != "state_change":
            return None
        terminal_time = _dt(result.event_time)
        window = result.meta.get("window") if isinstance(result.meta, dict) else None
        start = _dt(window.get("start")) if isinstance(window, dict) else None
        end = _dt(window.get("end")) if isinstance(window, dict) else None
        if terminal_time is None or start is None or end is None:
            return None

        history = await self.ha.get_history(request.entity_id, start, end, significant_only=False)
        timed: list[tuple[int, dict[str, Any], datetime]] = []
        for index, row in enumerate(history):
            when = _history_time(row)
            if when is not None:
                timed.append((index, row, when))
        terminal_candidates = [
            item
            for item in timed
            if str(item[1].get("state") or "") == terminal_state
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

        motion_row = history[terminal_index - 1]
        origin_row = history[terminal_index - 2]
        if str(motion_row.get("state") or "") != spec["motion"]:
            return None
        if str(origin_row.get("state") or "") != spec["origin"]:
            return None
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
        )
        anchor_result = await super().investigate(anchor_request)
        episode = {
            "recognized": True,
            "direction": spec["direction"],
            "origin_state": spec["origin"],
            "motion_state": spec["motion"],
            "terminal_state": terminal_state,
            "origin_time": origin_time.isoformat() if origin_time else None,
            "motion_start_time": motion_time.isoformat(),
            "terminal_time": matched_terminal_time.isoformat(),
            "motion_duration_seconds": duration,
            "rule": "adjacent_coherent_cover_states_not_temporal_proximity",
            "causal_anchor_status": anchor_result.status,
            "causal_anchor_event_time": anchor_result.event_time,
            "causal_anchor_used": False,
        }
        return episode, anchor_result

    @staticmethod
    def _naturalize_cover_observation(result: InvestigationResult) -> None:
        if not result.entity_id.startswith("cover.") or result.event_type != "state_change":
            return
        label = result.entity_name or result.entity_id
        after = result.observed.get("after")
        if after == "closed":
            result.observed["description"] = f"{label} s'est fermé."
        elif after == "open":
            result.observed["description"] = f"{label} s'est ouvert."
        elif after == "closing":
            result.observed["description"] = f"{label} se ferme."
        elif after == "opening":
            result.observed["description"] = f"{label} s'ouvre."

    async def _apply_cover_episode(
        self,
        request: InvestigationRequest,
        result: InvestigationResult,
    ) -> None:
        resolved = await self._cover_episode_anchor(request, result)
        self._naturalize_cover_observation(result)
        if resolved is None:
            return
        episode, anchor_result = resolved
        result.meta["cover_episode"] = episode

        anchor_cause_type = str(anchor_result.cause.get("type") or "unknown")
        if (
            _STATUS_RANK.get(anchor_result.status, 0) <= 0
            or anchor_cause_type in {"unknown", "multiple_candidates"}
        ):
            return

        # The terminal state remains the observed effect. Only the causal material comes
        # from the proven start of the same movement episode.
        if _STATUS_RANK.get(anchor_result.status, 0) >= _STATUS_RANK.get(result.status, 0):
            result.status = anchor_result.status
            result.cause = anchor_result.cause
            result.chain = list(anchor_result.chain)
            result.candidates = list(anchor_result.candidates)
            result.evidence.extend(anchor_result.evidence)
            result.limits = list(dict.fromkeys([*result.limits, *anchor_result.limits]))
            episode["causal_anchor_used"] = True

    async def _state_index(self) -> dict[str, dict[str, Any]]:
        states = await self._all_states()
        return {
            str(state.get("entity_id")): state
            for state in states
            if isinstance(state, dict) and state.get("entity_id")
        }

    async def _enrich_condition_labels(
        self,
        conditions: list[dict[str, Any]],
        state_index: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]] | None:
        if not conditions:
            return state_index
        if state_index is None:
            state_index = await self._state_index()
        for condition in conditions:
            state = state_index.get(str(condition.get("entity_id") or ""))
            if not isinstance(state, dict):
                continue
            attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
            if attrs.get("friendly_name"):
                condition["name"] = str(attrs["friendly_name"])
            if attrs.get("unit_of_measurement"):
                condition["unit"] = str(attrs["unit_of_measurement"])
        return state_index

    async def _enrich_human_cause(
        self,
        human_cause: dict[str, Any] | None,
        state_index: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]] | None:
        if not human_cause:
            return state_index
        detail = human_cause.get("detail")
        if not isinstance(detail, dict):
            return state_index
        entity_id = str(detail.get("entity_id") or "")
        if not entity_id:
            return state_index

        if state_index is None:
            state_index = await self._state_index()
        state = state_index.get(entity_id)
        if not isinstance(state, dict):
            return state_index
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        if attrs.get("friendly_name"):
            human_cause["entity_name"] = str(attrs["friendly_name"])
        if attrs.get("device_class"):
            human_cause["device_class"] = str(attrs["device_class"])
        if attrs.get("unit_of_measurement"):
            human_cause["unit"] = str(attrs["unit_of_measurement"])
        return state_index

    @staticmethod
    def _insert_conditions(result: InvestigationResult, conditions: list[dict[str, Any]]) -> None:
        if not conditions:
            return
        source_kind = result.cause.get("type")
        for index, step in enumerate(result.chain):
            if step.get("kind") == source_kind:
                result.chain[index:index] = conditions
                return
        result.chain.extend(conditions)

    async def investigate(self, request: InvestigationRequest) -> InvestigationResult:
        result = await self._investigate_with_adaptive_window(request)
        await self._apply_cover_episode(request, result)
        complete_confirmed_trace_chain(result)

        state_index: dict[str, dict[str, Any]] | None = None
        conditions = extract_passed_conditions(result)
        state_index = await self._enrich_condition_labels(conditions, state_index)
        self._insert_conditions(result, conditions)

        human_cause = (
            select_effect_linked_cause(result)
            or select_branch_decision_cause(result)
            or select_human_cause(result)
        )
        state_index = await self._enrich_human_cause(human_cause, state_index)
        if human_cause:
            text = human_cause_text(human_cause)
            if text:
                human_cause["text"] = text
            rule_text = human_rule_text(human_cause, result)
            if rule_text:
                human_cause["rule_text"] = rule_text

        detail_mode = normalize_detail_mode(request.detail_mode)
        detailed = detail_mode == "detailed"

        result.meta["base_version"] = BASE_VERSION
        result.meta["version"] = VERSION
        explanation = result.meta.setdefault("explanation", {})
        explanation["human_cause"] = human_cause
        explanation["human_cause_origin"] = human_cause.get("origin") if human_cause else None
        explanation["indeterminate_reason"] = bool(build_indeterminate_explanation(result))
        explanation["proven_conditions"] = len(conditions)
        explanation["detail_mode"] = detail_mode
        explanation["automation_name_requested"] = detailed
        explanation["rule_requested"] = detailed
        explanation["trace_interval_matching"] = True
        explanation["effect_command_matching"] = True
        explanation["cover_episode_matching"] = True

        human = build_human_causal_answer(
            result,
            include_automation_name=detailed,
            include_rule=detailed,
        )
        explanation["human_causal_chain"] = bool(human)
        if human:
            result.answer_text = human
        else:
            result.answer_text = self._build_answer(result)
        return result
