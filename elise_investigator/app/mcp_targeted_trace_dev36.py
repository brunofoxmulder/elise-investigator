from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from causal_utils import walk_contains
from mcp_client import MCPReadOnlyError
from mcp_trace_explorer import _unwrap_tool_result

_TRACE_TOOL = "ha_get_automation_traces"
_MAX_DISTANCE_SECONDS = 300.0


def _dt(value: Any) -> datetime | None:
    if isinstance(value, dict):
        value = value.get("start")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _trace_distance(event_time: datetime, trace: dict[str, Any]) -> float | None:
    stamp = trace.get("timestamp")
    if isinstance(stamp, dict):
        start = _dt(stamp.get("start"))
        finish = _dt(stamp.get("finish"))
        if start is None:
            return None
        if finish is not None and finish >= start:
            if start <= event_time <= finish:
                return 0.0
            if event_time > finish:
                return (event_time - finish).total_seconds()
        return abs((start - event_time).total_seconds())
    start = _dt(stamp)
    return abs((start - event_time).total_seconds()) if start is not None else None


def _rawish_detail(payload: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the small raw-trace shape used by Investigator's proven parsers.

    HA-MCP deliberately formats trace nodes, but keeps path/result/variables.
    Re-indexing them by path restores the runtime structure without inventing data.
    """
    detail: dict[str, Any] = {
        key: payload.get(key)
        for key in ("run_id", "timestamp", "state", "trigger", "config", "error")
        if payload.get(key) is not None
    }
    trace: dict[str, list[dict[str, Any]]] = {}
    actions = payload.get("action_trace")
    if isinstance(actions, list):
        for item in actions:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "")
            if not path:
                continue
            trace.setdefault(path, []).append(dict(item))
    if trace:
        detail["trace"] = trace
    return detail


def _targets_entity(detail: dict[str, Any], entity_id: str) -> bool:
    trace = detail.get("trace")
    if not isinstance(trace, dict):
        return False
    for raw_nodes in trace.values():
        nodes = raw_nodes if isinstance(raw_nodes, list) else [raw_nodes]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            result = node.get("result")
            params = result.get("params") if isinstance(result, dict) else None
            if isinstance(params, dict) and params.get("domain") and params.get("service"):
                if walk_contains(params.get("target"), entity_id):
                    return True
    return False


class MCPTargetedTraceReader:
    """Read at most three trace summaries and one detail for one known source."""

    def __init__(self, mcp_client):
        self.client = mcp_client
        self.list_calls = 0
        self.detail_calls = 0

    async def nearest_detail(
        self, source_entity_id: str, event_time: datetime, target_entity_id: str
    ) -> dict[str, Any] | None:
        try:
            _, protocol = await self.client.open_protocol()
            raw = await protocol.call_tool(
                _TRACE_TOOL,
                {
                    "automation_id": source_entity_id,
                    "limit": 3,
                    "offset": 0,
                    "order": "newest",
                },
            )
            self.list_calls += 1
            payload = _unwrap_tool_result(raw)
            traces = payload.get("traces")
            if not isinstance(traces, list):
                return None

            candidates: list[tuple[float, str]] = []
            for trace in traces[:3]:
                if not isinstance(trace, dict):
                    continue
                run_id = trace.get("run_id")
                distance = _trace_distance(event_time, trace)
                if isinstance(run_id, str) and distance is not None and distance <= _MAX_DISTANCE_SECONDS:
                    candidates.append((distance, run_id))
            if not candidates:
                return None
            candidates.sort(key=lambda item: (item[0], item[1]))
            run_id = candidates[0][1]

            raw_detail = await protocol.call_tool(
                _TRACE_TOOL,
                {
                    "automation_id": source_entity_id,
                    "run_id": run_id,
                    "deduplicate": True,
                    "detailed": False,
                    "sections": "trigger,conditions,actions,config,error",
                },
            )
            self.detail_calls += 1
            detail_payload = _unwrap_tool_result(raw_detail)
            detail = _rawish_detail(detail_payload)
            if not _targets_entity(detail, target_entity_id):
                return None
            return detail
        except MCPReadOnlyError:
            return None
