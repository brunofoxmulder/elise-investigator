from __future__ import annotations

from typing import Any

from action_effect_cause import select_effect_linked_cause
from branch_decision_cause_dev62 import select_branch_decision_cause
from causal_recorder import CausalRecord
from human_cause import select_human_cause
from models import Evidence, InvestigationResult
from proof_policy import executed_trace_actions
from targeted_memory_enricher_dev63 import TargetedMemoryEnricher as Dev63TargetedMemoryEnricher
from targeted_memory_enricher_dev36 import _compact_human_cause
from trace_action_local_dev68 import (
    select_completed_wait_cause,
    select_elapsed_delay_cause,
    select_trigger_with_true_conditions,
)
from trace_final_action_dev63 import select_chosen_branch_conditions, select_wait_timeout_cause
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text


class TargetedMemoryEnricher(Dev63TargetedMemoryEnricher):
    """dev.68: keep dev.67 successes and fix only exact action-local trace shapes."""

    async def _trigger_conditions_text(self, cause: dict[str, Any]) -> str | None:
        detail = cause.get("detail")
        if not isinstance(detail, dict):
            return None
        trigger = detail.get("trigger")
        conditions = detail.get("conditions")
        if not isinstance(trigger, dict) or not isinstance(conditions, list) or not conditions:
            return None

        atoms: list[dict[str, Any]] = [
            {
                "kind": "automation_trigger",
                "origin": "automation_trigger",
                "proven": True,
                "detail": dict(trigger),
            }
        ]
        atoms.extend(
            {
                "kind": "branch_decision",
                "origin": "choose_condition",
                "proven": True,
                "detail": dict(item),
            }
            for item in conditions
            if isinstance(item, dict)
        )
        if len(atoms) != len(conditions) + 1:
            return None

        texts: list[str] = []
        for atom in atoms:
            await self._label_cause(atom)
            text = human_cause_text(atom)
            if not text:
                return None
            texts.append(text.rstrip("."))
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

        # Preserve all dev.67 selectors. dev.68 only inserts bounded action-local
        # shapes before the generic automation-start trigger fallback.
        human_cause = select_effect_linked_cause(result)
        if human_cause is None:
            human_cause = select_completed_wait_cause(result)
        if human_cause is None:
            human_cause = select_wait_timeout_cause(result)
        if human_cause is None:
            human_cause = select_elapsed_delay_cause(result)
        if human_cause is None:
            human_cause = select_chosen_branch_conditions(result)
        if human_cause is None:
            human_cause = select_trigger_with_true_conditions(result)
        if human_cause is None:
            human_cause = select_branch_decision_cause(result)
        if human_cause is None:
            human_cause = select_human_cause(result)

        text: str | None = None
        origin = human_cause.get("origin") if isinstance(human_cause, dict) else None
        if origin == "wait_timeout":
            duration = human_cause.get("detail", {}).get("duration_text")
            if duration:
                text = f"la durée maximale de {duration} a été atteinte"
        elif origin == "delay_elapsed":
            duration = human_cause.get("detail", {}).get("duration_text")
            if duration:
                text = f"le délai de {duration} s'est écoulé"
        elif origin == "choose_conditions":
            text = await self._conjunction_text(human_cause)
        elif origin == "trigger_plus_conditions":
            text = await self._trigger_conditions_text(human_cause)
        else:
            await self._label_cause(human_cause)
            text = human_cause_text(human_cause) if human_cause else None

        return text, run_id, _compact_human_cause(human_cause)
