from __future__ import annotations

from typing import Any

from causal_resolver_rc11 import unique_effect_command_rc11
from causal_resolver_rc12 import resolve_cause_rc12
from cover_cause_v2 import periodic_position_decision
from targeted_memory_enricher_dev36 import _compact_human_cause
from targeted_memory_enricher_rc11 import TargetedMemoryEnricherRC11


class TargetedMemoryEnricherRC12(TargetedMemoryEnricherRC11):
    """Keep RC11 trace selection and rendering; complete missing trigger facts."""

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
        cause = resolve_cause_rc12(result, registry)
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
