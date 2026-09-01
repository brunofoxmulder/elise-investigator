from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecord
from context_linked_effect_cause_dev50 import select_context_linked_effect_cause
from human_cause import select_human_cause
from models import Evidence, InvestigationResult
from targeted_memory_enricher_dev36 import _compact_human_cause
from targeted_memory_enricher_dev49 import TargetedMemoryEnricher as Dev49TargetedMemoryEnricher
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text


class TargetedMemoryEnricher(Dev49TargetedMemoryEnricher):
    """Dev.50 adds one narrow nested-trace fallback for exact context-linked effects."""

    async def _reason_from_detail(
        self,
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
        detail: dict[str, Any],
        run_id: str | None,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        strict = await super()._reason_from_detail(
            record,
            source_entity_id,
            source_name,
            source_kind,
            detail,
            run_id,
        )
        if strict[0] is not None or strict[2] is not None:
            return strict
        if not self._context_link_proven(record, source_entity_id, source_kind):
            return strict

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
                    summary="Trace exacte de la source déjà liée à l'effet par le contexte Home Assistant",
                    source=source_entity_id,
                    strength="direct",
                    raw=detail,
                )
            ],
        )
        complete_confirmed_trace_chain(result)
        human_cause = select_context_linked_effect_cause(result) or select_human_cause(result)
        await self._label_cause(human_cause)
        text = human_cause_text(human_cause) if human_cause else None
        return text, run_id, _compact_human_cause(human_cause)
