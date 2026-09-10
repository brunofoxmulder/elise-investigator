from __future__ import annotations

from typing import Any

from action_effect_cause import select_effect_linked_cause
from causal_recorder import CausalRecord
from human_cause import _proven_start_trigger, select_human_cause
from models import Evidence, InvestigationResult
from proof_policy import executed_trace_actions
from targeted_memory_enricher_dev36 import _compact_human_cause
from targeted_memory_enricher_dev71 import TargetedMemoryEnricher as Dev71TargetedMemoryEnricher
from trace_action_local_dev68 import (
    select_completed_wait_cause,
    select_elapsed_delay_cause,
    select_trigger_with_true_conditions,
)
from trace_action_local_dev71 import select_adjacent_temporal_cause
from trace_branch_path_dev70 import select_executed_branch_conditions
from trace_final_action_dev63 import select_wait_timeout_cause
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text


class TargetedMemoryEnricher(Dev71TargetedMemoryEnricher):
    """dev.72: keep dev.71, but do not elevate pure state guards as causal factors.

    Exact trace proves that a condition was true; that alone does not prove that a
    discrete state guard (mode enabled, auxiliary switch on, etc.) is part of the
    human cause. Existing proven threshold conjunctions remain supported when at
    least one exact-trace condition is numeric_state.
    """

    @staticmethod
    def _has_numeric_condition(candidate: dict[str, Any] | None) -> bool:
        if not isinstance(candidate, dict):
            return False
        detail = candidate.get("detail")
        if not isinstance(detail, dict):
            return False
        conditions = detail.get("conditions")
        if not isinstance(conditions, list):
            return False
        return any(
            isinstance(item, dict)
            and str(item.get("platform") or item.get("condition") or "").casefold() == "numeric_state"
            for item in conditions
        )

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
            evidence=[Evidence(kind="trace", summary="Trace ciblée de la source indiquée par Activity", source=source_entity_id, strength="direct", raw=detail)],
        )
        complete_confirmed_trace_chain(result)

        human_cause = select_effect_linked_cause(result)
        if human_cause is None:
            human_cause = select_completed_wait_cause(result)
        if human_cause is None:
            human_cause = select_wait_timeout_cause(result)
        if human_cause is None:
            human_cause = select_elapsed_delay_cause(result)
        if human_cause is None:
            human_cause = select_adjacent_temporal_cause(result)

        # A trace can prove a guard was true without proving it belongs in the human
        # causal sentence. Preserve the already validated threshold conjunction case,
        # but never promote a bundle made only of discrete state guards.
        if human_cause is None:
            combined = select_trigger_with_true_conditions(result)
            trigger = _proven_start_trigger(result)
            platform = str((trigger or {}).get("platform") or (trigger or {}).get("trigger") or "").casefold()
            if (
                combined is not None
                and platform in {"state", "numeric_state"}
                and self._has_numeric_condition(combined)
            ):
                human_cause = combined

        if human_cause is None:
            branch = select_executed_branch_conditions(result)
            trigger = _proven_start_trigger(result)
            platform = str((trigger or {}).get("platform") or (trigger or {}).get("trigger") or "").casefold()
            if (
                isinstance(branch, dict)
                and platform in {"state", "numeric_state"}
                and self._has_numeric_condition(branch)
            ):
                human_cause = self._combine_trigger_and_branch(trigger, branch)

        if human_cause is None and select_adjacent_temporal_cause(result) is None:
            candidate = select_human_cause(result)
            if isinstance(candidate, dict):
                origin = candidate.get("origin")
                if origin != "automation_trigger" or not self._has_any_executed_temporal_barrier(result):
                    # Generic fallback may retain only the proven start trigger. It must
                    # not re-introduce condition arrays that dev.72 deliberately rejected.
                    if origin == "trigger_plus_conditions" and not self._has_numeric_condition(candidate):
                        trigger = _proven_start_trigger(result)
                        human_cause = {
                            "kind": "automation_trigger",
                            "origin": "automation_trigger",
                            "path": "trigger/0",
                            "proven": True,
                            "detail": dict(trigger),
                        } if isinstance(trigger, dict) and trigger else None
                    else:
                        human_cause = candidate

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
        elif origin == "trigger_plus_conditions":
            text = await self._trigger_conditions_text(human_cause)
        else:
            await self._label_cause(human_cause)
            text = human_cause_text(human_cause) if human_cause else None

        return text, run_id, _compact_human_cause(human_cause)
