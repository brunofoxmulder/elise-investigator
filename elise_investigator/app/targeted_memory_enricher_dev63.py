from __future__ import annotations

from typing import Any

from action_effect_cause import select_effect_linked_cause
from branch_decision_cause_dev62 import select_branch_decision_cause
from causal_recorder import CausalRecord
from human_cause import select_human_cause
from models import Evidence, InvestigationResult
from proof_policy import executed_trace_actions
from targeted_memory_enricher_dev36 import TargetedMemoryEnricher as Dev36TargetedMemoryEnricher, _compact_human_cause
from trace_final_action_dev63 import select_chosen_branch_conditions, select_wait_timeout_cause
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text


class TargetedMemoryEnricher(Dev36TargetedMemoryEnricher):
    """dev.63: explain the exact final action before falling back to start trigger."""

    async def _conjunction_text(self, cause: dict[str, Any]) -> str | None:
        detail = cause.get("detail")
        conditions = detail.get("conditions") if isinstance(detail, dict) else None
        if not isinstance(conditions, list) or not conditions:
            return None
        texts: list[str] = []
        for item in conditions:
            if not isinstance(item, dict):
                return None
            atom = {
                "kind": "branch_decision",
                "origin": "choose_condition",
                "proven": True,
                "detail": dict(item),
            }
            await self._label_cause(atom)
            text = human_cause_text(atom)
            if not text:
                return None
            texts.append(text.rstrip("."))
        if len(texts) == 1:
            return texts[0]
        if len(texts) == 2:
            return f"{texts[0]} et {texts[1]}"
        return ", ".join(texts[:-1]) + f" et {texts[-1]}"

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
                    summary="Trace ciblée de la source indiquée par Activity",
                    source=source_entity_id,
                    strength="direct",
                    raw=detail,
                )
            ],
        )
        complete_confirmed_trace_chain(result)

        human_cause = select_effect_linked_cause(result)
        if human_cause is None:
            human_cause = select_wait_timeout_cause(result)
        if human_cause is None:
            human_cause = select_chosen_branch_conditions(result)
        if human_cause is None:
            human_cause = select_branch_decision_cause(result)
        if human_cause is None:
            human_cause = select_human_cause(result)

        text: str | None = None
        if human_cause and human_cause.get("origin") == "wait_timeout":
            duration = human_cause.get("detail", {}).get("duration_text")
            if duration:
                text = f"la durée maximale de {duration} a été atteinte"
        elif human_cause and human_cause.get("origin") == "choose_conditions":
            text = await self._conjunction_text(human_cause)
        else:
            await self._label_cause(human_cause)
            text = human_cause_text(human_cause) if human_cause else None

        return text, run_id, _compact_human_cause(human_cause)
