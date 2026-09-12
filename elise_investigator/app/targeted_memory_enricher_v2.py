from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from causal_recorder import CausalRecord
from causal_renderer_v2 import CausalRendererV2
from causal_resolver_v2 import resolve_cause, unique_effect_command
from cover_cause_v2 import periodic_position_decision
from investigator import _extract_trace_start, _trace_run_id
from models import Evidence, InvestigationResult
from targeted_memory_enricher_dev36 import (
    TargetedMemoryEnricher as BaseTargetedMemoryEnricher,
    _compact_human_cause,
)
from trigger_semantics import complete_confirmed_trace_chain


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class TargetedMemoryEnricherV2(BaseTargetedMemoryEnricher):
    """Action-aware trace enrichment with one resolver and one renderer.

    This class deliberately inherits only the bounded read-only plumbing from dev.36.
    It does not inherit the dev.68->70->71->72 causal policy chain.
    """

    MAX_DIRECT_TRACE_CANDIDATES = 12

    def __init__(self, ha, trace_investigator):
        super().__init__(ha, trace_investigator)
        self.renderer = CausalRendererV2(ha)

    @staticmethod
    def _result(
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
        detail: dict[str, Any],
    ) -> InvestigationResult:
        result = InvestigationResult(
            status="confirmed",
            entity_id=record.entity_id,
            entity_name=record.entity_name,
            event_type=record.event_kind,
            event_time=record.event_time,
            observed={
                "before": record.before_value,
                "after": record.after_value,
                "attribute": record.attribute,
            },
            cause={
                "type": source_kind,
                "entity_id": source_entity_id,
                "name": source_name,
                "system_confirmed": True,
            },
            evidence=[
                Evidence(
                    kind="trace",
                    summary="Trace ciblée de la source indiquée par Activity",
                    source=source_entity_id,
                    strength="direct",
                    raw=detail,
                )
            ],
        )
        complete_confirmed_trace_chain(result)
        return result

    @staticmethod
    def _command_runtime_distance(
        result: InvestigationResult,
        command_path: str,
        event_time: datetime,
    ) -> float | None:
        detail = next(
            (
                evidence.raw
                for evidence in result.evidence
                if evidence.kind == "trace" and isinstance(evidence.raw, dict)
            ),
            None,
        )
        trace = detail.get("trace") if isinstance(detail, dict) else None
        if not isinstance(trace, dict):
            return None
        raw = trace.get(command_path)
        nodes = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
        distances: list[float] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            when = _dt(node.get("timestamp"))
            if when is not None:
                distances.append(abs((when - event_time).total_seconds()))
        return min(distances) if distances else None

    async def _reason_from_detail(
        self,
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
        detail: dict[str, Any],
        run_id: str | None,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        result = self._result(record, source_entity_id, source_name, source_kind, detail)
        cause = resolve_cause(result)
        if not isinstance(cause, dict):
            return None, run_id, None

        # Cover-only informational refinement. Keep the V2 resolver's proven trigger,
        # but when that trigger is periodic and the exact action is set_cover_position,
        # include the requested position. This does not promote branch guards to causes
        # and does not change any non-cover causal path.
        if (
            result.entity_id.startswith("cover.")
            and str(cause.get("origin") or "") == "automation_trigger"
        ):
            command = unique_effect_command(result)
            trigger = cause.get("detail") if isinstance(cause.get("detail"), dict) else None
            enriched = periodic_position_decision(result, command or {}, trigger)
            if isinstance(enriched, dict):
                cause = enriched

        text = await self.renderer.render(cause)
        if not text:
            return None, run_id, _compact_human_cause(cause)
        return text, run_id, _compact_human_cause(cause)

    async def _direct_action_aware_detail(
        self,
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Select a source trace by the executed target command, not trace start age.

        Trace-start proximity only orders which summaries are read. Acceptance requires a
        unique runtime command matching the observed target effect. When several runs
        match, command-node timestamp proximity chooses only a unique best run.
        """
        try:
            resolved = await self.trace_investigator._config_id_for_entity(source_entity_id)
        except Exception:
            return None, None
        if not resolved:
            return None, None
        domain, item_id = resolved
        try:
            summaries = await self.ha.list_traces(domain, item_id)
            self.trace_reads += 1
        except Exception:
            self.direct_trace_failures += 1
            return None, None
        if not summaries:
            return None, None

        event_time = record.normalized_time()
        ranked: list[tuple[float, dict[str, Any]]] = []
        for summary in summaries:
            start = _extract_trace_start(summary)
            distance = abs((start - event_time).total_seconds()) if start else float("inf")
            ranked.append((distance, summary))
        ranked.sort(key=lambda item: item[0])

        matches: list[tuple[float | None, float, dict[str, Any], str]] = []
        for summary_distance, summary in ranked[: self.MAX_DIRECT_TRACE_CANDIDATES]:
            run_id = _trace_run_id(summary)
            if not run_id:
                continue
            try:
                detail = await self.ha.get_trace(domain, item_id, run_id)
            except Exception:
                self.direct_trace_failures += 1
                continue
            if not isinstance(detail, dict):
                continue
            result = self._result(record, source_entity_id, source_name, source_kind, detail)
            command = unique_effect_command(result)
            if not isinstance(command, dict):
                continue
            path = str(command.get("path") or "")
            runtime_distance = self._command_runtime_distance(result, path, event_time)
            matches.append((runtime_distance, summary_distance, detail, run_id))

        if not matches:
            return None, None
        if len(matches) == 1:
            return matches[0][2], matches[0][3]

        timed = [item for item in matches if item[0] is not None]
        if timed:
            timed.sort(key=lambda item: (float(item[0]), item[1]))
            best = timed[0]
            if len(timed) == 1 or float(timed[1][0]) > float(best[0]):
                return best[2], best[3]
            return None, None

        # Several exact-effect traces without runtime command timestamps are ambiguous.
        return None, None

    async def _trace_reason(
        self,
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        detail, run_id = await self._direct_action_aware_detail(
            record,
            source_entity_id,
            source_name,
            source_kind,
        )
        if isinstance(detail, dict):
            self.last_trace_backend = "direct_ha_action_aware"
            return await self._reason_from_detail(
                record,
                source_entity_id,
                source_name,
                source_kind,
                detail,
                run_id,
            )

        # Preserve the already-existing read-only MCP fallback when direct trace access is
        # unavailable. The V2 resolver still decides semantics on the returned detail.
        reader = self.mcp_trace_reader
        if reader is not None:
            detail = await reader.nearest_detail(
                source_entity_id, record.normalized_time(), record.entity_id
            )
            if isinstance(detail, dict):
                self.last_trace_backend = "ha_mcp"
                return await self._reason_from_detail(
                    record,
                    source_entity_id,
                    source_name,
                    source_kind,
                    detail,
                    str(detail.get("run_id")) if detail.get("run_id") else None,
                )
        return None, run_id, None
