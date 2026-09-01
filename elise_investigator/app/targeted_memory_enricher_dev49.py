from __future__ import annotations

from typing import Any

from action_effect_cause import select_effect_linked_cause
from branch_decision_cause import select_branch_decision_cause
from causal_recorder import CausalRecord
from human_cause import select_human_cause
from models import Evidence, InvestigationResult
from targeted_memory_enricher_dev36 import _compact_human_cause
from targeted_memory_enricher_dev48 import TargetedMemoryEnricher as Dev48TargetedMemoryEnricher
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text


class TargetedMemoryEnricher(Dev48TargetedMemoryEnricher):
    """Dev.49 restores causal detail for context-linked device actions.

    Some Home Assistant device actions are represented in the runtime trace without
    the canonical entity_id in the service target. The strict generic proof helper
    therefore cannot re-prove the target even though the causal recorder already
    captured the exact automation/script context that produced the state effect.

    This fallback is deliberately narrow: non-cover, primary off<->on only, and the
    source kind/entity must exactly match the context already captured on the effect.
    Cover episode semantics are not changed.
    """

    @staticmethod
    def _context_link_proven(
        record: CausalRecord,
        source_entity_id: str,
        source_kind: str,
    ) -> bool:
        if record.entity_id.startswith("cover.") or record.attribute is not None:
            return False
        if record.origin_type != source_kind or source_kind not in {"automation", "script"}:
            return False
        if record.source_entity_id != source_entity_id:
            return False
        pair = (
            str(record.before_value).strip().casefold(),
            str(record.after_value).strip().casefold(),
        )
        return pair in {("off", "on"), ("on", "off")}

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

        # The event-stream context already proves source -> effect. We may therefore
        # use that exact source trace to recover the decisive trigger/wait/condition
        # even when HA's device-action trace omits the canonical target entity_id.
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
                    summary="Trace ciblée d'une source déjà liée à l'effet par le contexte Home Assistant",
                    source=source_entity_id,
                    strength="direct",
                    raw=detail,
                )
            ],
        )
        complete_confirmed_trace_chain(result)
        human_cause = (
            select_effect_linked_cause(result)
            or select_branch_decision_cause(result)
            or select_human_cause(result)
        )
        await self._label_cause(human_cause)
        text = human_cause_text(human_cause) if human_cause else None
        return text, run_id, _compact_human_cause(human_cause)
