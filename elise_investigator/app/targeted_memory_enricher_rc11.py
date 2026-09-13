from __future__ import annotations

from datetime import datetime
from typing import Any

from causal_resolver_rc11 import resolve_cause_rc11, unique_effect_command_rc11
from cover_cause_v2 import periodic_position_decision
from investigator import _extract_trace_start, _trace_run_id
from targeted_memory_enricher_dev36 import _compact_human_cause
from targeted_memory_enricher_rc9 import TargetedMemoryEnricherRC9
from targeted_memory_enricher_v2 import _select_unique_trace_match


class TargetedMemoryEnricherRC11(TargetedMemoryEnricherRC9):
    """RC11 recovers missing command params from the exact executed config path."""

    async def _registry_entry(self, entity_id: str) -> dict[str, Any] | None:
        getter = getattr(self.ha, "get_entity_registry", None)
        if getter is None:
            return None
        try:
            entry = await getter(entity_id)
        except Exception:
            return None
        return entry if isinstance(entry, dict) else None

    async def _reason_from_detail(
        self,
        record,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
        detail: dict[str, Any],
        run_id: str | None,
    ):
        result = self._result(record, source_entity_id, source_name, source_kind, detail)
        registry = await self._registry_entry(record.entity_id)
        cause = resolve_cause_rc11(result, registry)
        if not isinstance(cause, dict):
            return None, run_id, None

        if (
            result.entity_id.startswith("cover.")
            and str(cause.get("origin") or "") == "automation_trigger"
        ):
            command = unique_effect_command_rc11(result, registry)
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
        record,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
    ):
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

        registry = await self._registry_entry(record.entity_id)
        event_time: datetime = record.normalized_time()
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
            command = unique_effect_command_rc11(result, registry)
            if not isinstance(command, dict):
                continue
            path = str(command.get("path") or "")
            runtime_distance = self._command_runtime_distance(result, path, event_time)
            matches.append((runtime_distance, summary_distance, detail, run_id))

        selected = _select_unique_trace_match(matches)
        if selected is None:
            return None, None
        return selected[2], selected[3]

