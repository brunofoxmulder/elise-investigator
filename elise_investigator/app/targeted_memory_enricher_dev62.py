from __future__ import annotations

from typing import Any

from action_effect_cause import select_effect_linked_cause
from branch_decision_cause_dev62 import select_branch_decision_cause
from causal_recorder import CausalRecord
from human_cause import select_human_cause
from models import Evidence, InvestigationResult
from proof_policy import executed_trace_actions
from targeted_memory_enricher_dev36 import TargetedMemoryEnricher as Dev36TargetedMemoryEnricher, _compact_human_cause
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text


class TargetedMemoryEnricher(Dev36TargetedMemoryEnricher):
    """dev.62 exact-trace interpreter.

    Only the semantic selection inside the already-targeted trace changes: a
    runtime-proven choose condition that led to the matching target action is
    preferred over the automation's technical start trigger.
    """

    async def _reason_from_detail(
        self,
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
        detail: dict[str, Any],
        run_id: str | None,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        if not executed_trace_actions(detail, record.entity_id):
            return None, run_id, None

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
                    summary="Trace ciblée de la source indiquée par le Logbook",
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
