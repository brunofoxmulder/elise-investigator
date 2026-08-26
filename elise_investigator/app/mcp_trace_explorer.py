from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from mcp_client import MCPProtocolSession, MCPReadOnlyError

TRACE_TOOL_NAME = "ha_get_automation_traces"
MAX_CANDIDATES = 6
TRACE_LIST_LIMIT = 3
MAX_EVENT_DISTANCE_SECONDS = 30 * 60
MAX_CONDITIONS = 12
MAX_ACTIONS = 20
DETAIL_SECTIONS = "trigger,conditions,actions,error"


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _unwrap_tool_result(value: Any) -> dict[str, Any]:
    """Extract the structured payload returned by FastMCP without guessing."""
    if not isinstance(value, dict):
        return {}

    for key in ("structuredContent", "structured_content"):
        candidate = value.get(key)
        if isinstance(candidate, dict):
            return candidate

    content = value.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    return value


def _observed_event_time(local_synthesis: dict[str, Any]) -> str | None:
    facts = local_synthesis.get("facts")
    if not isinstance(facts, list):
        return None
    for fact in facts:
        if not isinstance(fact, dict) or fact.get("type") != "recent_history":
            continue
        events = fact.get("events")
        if not isinstance(events, list) or not events:
            return None
        first = events[0]
        if isinstance(first, dict):
            value = first.get("time")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _configuration_leads(local_synthesis: dict[str, Any]) -> list[dict[str, str | None]]:
    raw = local_synthesis.get("configuration_leads")
    if not isinstance(raw, list):
        return []
    leads: list[dict[str, str | None]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id.startswith(("automation.", "script.")):
            continue
        name = item.get("name")
        leads.append(
            {
                "entity_id": entity_id,
                "name": name.strip() if isinstance(name, str) and name.strip() else None,
            }
        )
        if len(leads) >= MAX_CANDIDATES:
            break
    return leads


def _compact_trace_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    traces = payload.get("traces")
    if not isinstance(traces, list):
        return []
    compact: list[dict[str, Any]] = []
    for trace in traces[:TRACE_LIST_LIMIT]:
        if not isinstance(trace, dict):
            continue
        item = {
            key: trace.get(key)
            for key in ("run_id", "timestamp", "state", "trigger", "error")
            if trace.get(key) is not None
        }
        compact.append(item)
    return compact


def _compact_detail(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep causal structure while dropping large variable payloads."""
    compact: dict[str, Any] = {
        key: payload.get(key)
        for key in ("success", "automation_id", "run_id", "timestamp", "state", "error")
        if payload.get(key) is not None
    }

    trigger = payload.get("trigger")
    if isinstance(trigger, dict):
        compact["trigger"] = trigger

    conditions = payload.get("condition_results")
    if isinstance(conditions, list):
        clean_conditions = [item for item in conditions if isinstance(item, dict)]
        compact["condition_results"] = clean_conditions[:MAX_CONDITIONS]
        compact["condition_count"] = len(clean_conditions)
        compact["conditions_truncated"] = len(clean_conditions) > MAX_CONDITIONS

    actions = payload.get("action_trace")
    if isinstance(actions, list):
        clean_actions: list[dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            # Variables can dominate a trace response. Dev.26 deliberately keeps
            # only execution structure and results, never the variable snapshots.
            clean_actions.append(
                {
                    key: action.get(key)
                    for key in ("path", "timestamp", "result", "error", "child_id")
                    if action.get(key) is not None
                }
            )
        compact["action_trace"] = clean_actions[:MAX_ACTIONS]
        compact["action_count"] = len(clean_actions)
        compact["actions_truncated"] = len(clean_actions) > MAX_ACTIONS

    return compact


def _error_result(reason: str, *, observed_event_time: str | None = None) -> dict[str, Any]:
    return {
        "mode": "bounded_read_only_trace_exploration",
        "read_only": True,
        "uses_llm": False,
        "trace_tool_called": False,
        "candidate_limit": MAX_CANDIDATES,
        "trace_list_limit": TRACE_LIST_LIMIT,
        "detail_limit": 1,
        "observed_event_time": observed_event_time,
        "candidates_queried": 0,
        "candidate_trace_lists": [],
        "selected_run": None,
        "selected_run_detail": None,
        "selection_is_causal_proof": False,
        "causal_verdict": None,
        "investigator_status_unchanged": True,
        "status": "not_run",
        "reason": reason,
    }


async def explore_bounded_traces(
    protocol: MCPProtocolSession,
    local_synthesis: dict[str, Any],
    sanitize: Callable[[Any], Any],
) -> dict[str, Any]:
    """Explore a small trace set without assigning causal certainty.

    Selection uses only temporal proximity to the latest observed Home Assistant
    history event. It is an investigation hint, never a causal verdict.
    """
    observed_event_time = _observed_event_time(local_synthesis)
    anchor = _parse_timestamp(observed_event_time)
    if anchor is None:
        return _error_result(
            "Aucun événement History horodaté utilisable pour borner les traces.",
            observed_event_time=observed_event_time,
        )

    candidates = _configuration_leads(local_synthesis)
    if not candidates:
        return _error_result(
            "Aucun candidat automation/script issu de la recherche de configuration.",
            observed_event_time=observed_event_time,
        )

    tool = protocol.tools.get(TRACE_TOOL_NAME)
    annotations = tool.get("annotations") if isinstance(tool, dict) else None
    if not isinstance(annotations, dict) or annotations.get("readOnlyHint") is not True:
        return _error_result(
            "ha_get_automation_traces n'est pas disponible avec readOnlyHint=true.",
            observed_event_time=observed_event_time,
        )

    candidate_lists: list[dict[str, Any]] = []
    scored_runs: list[tuple[float, str, str, dict[str, Any]]] = []
    trace_tool_called = False

    for candidate in candidates:
        entity_id = str(candidate["entity_id"])
        trace_tool_called = True
        try:
            raw = await protocol.call_tool(
                TRACE_TOOL_NAME,
                {
                    "automation_id": entity_id,
                    "limit": TRACE_LIST_LIMIT,
                    "offset": 0,
                    "order": "newest",
                },
            )
            payload = _unwrap_tool_result(raw)
            traces = _compact_trace_list(payload)
            candidate_lists.append(
                {
                    "entity_id": entity_id,
                    "name": candidate.get("name"),
                    "success": True,
                    "trace_count": payload.get("trace_count", len(traces)),
                    "total_available": payload.get("total_available"),
                    "has_more": payload.get("has_more"),
                    "traces": sanitize(traces),
                }
            )
            for trace in traces:
                run_id = trace.get("run_id")
                timestamp = trace.get("timestamp")
                parsed = _parse_timestamp(timestamp)
                if not isinstance(run_id, str) or parsed is None:
                    continue
                distance = abs((parsed - anchor).total_seconds())
                if distance <= MAX_EVENT_DISTANCE_SECONDS:
                    scored_runs.append((distance, entity_id, run_id, trace))
        except MCPReadOnlyError as exc:
            candidate_lists.append(
                {
                    "entity_id": entity_id,
                    "name": candidate.get("name"),
                    "success": False,
                    "error": sanitize(str(exc)),
                    "traces": [],
                }
            )

    selected_run: dict[str, Any] | None = None
    selected_detail: dict[str, Any] | None = None
    if scored_runs:
        scored_runs.sort(key=lambda item: item[0])
        distance, entity_id, run_id, trace = scored_runs[0]
        selected_run = {
            "automation_id": entity_id,
            "run_id": run_id,
            "timestamp": trace.get("timestamp"),
            "state": trace.get("state"),
            "trigger": trace.get("trigger"),
            "distance_seconds": distance,
            "selection_reason": "closest_trace_start_within_30_minutes",
            "selection_is_causal_proof": False,
        }
        try:
            raw_detail = await protocol.call_tool(
                TRACE_TOOL_NAME,
                {
                    "automation_id": entity_id,
                    "run_id": run_id,
                    "deduplicate": True,
                    "detailed": False,
                    "sections": DETAIL_SECTIONS,
                },
            )
            selected_detail = sanitize(_compact_detail(_unwrap_tool_result(raw_detail)))
        except MCPReadOnlyError as exc:
            selected_detail = {"success": False, "error": sanitize(str(exc))}

    return {
        "mode": "bounded_read_only_trace_exploration",
        "read_only": True,
        "uses_llm": False,
        "trace_tool_called": trace_tool_called,
        "candidate_limit": MAX_CANDIDATES,
        "trace_list_limit": TRACE_LIST_LIMIT,
        "detail_limit": 1,
        "detail_sections": DETAIL_SECTIONS,
        "observed_event_time": observed_event_time,
        "max_event_distance_seconds": MAX_EVENT_DISTANCE_SECONDS,
        "candidates_queried": len(candidates),
        "candidate_trace_lists": candidate_lists,
        "selected_run": selected_run,
        "selected_run_detail": selected_detail,
        "selection_is_causal_proof": False,
        "causal_verdict": None,
        "investigator_status_unchanged": True,
        "status": "detail_selected" if selected_detail is not None else "lists_only",
        "policy": (
            "La proximité temporelle sert uniquement à choisir une trace à examiner. "
            "Elle ne constitue pas une preuve causale et ne modifie jamais le verdict Investigator."
        ),
    }
