from __future__ import annotations

from typing import Any

from action_effect_cause import select_effect_linked_cause
from branch_decision_cause_dev62 import select_branch_decision_cause
from causal_recorder import CausalRecord
from human_cause import _proven_start_trigger, select_human_cause
from models import Evidence, InvestigationResult
from proof_policy import executed_trace_actions
from targeted_memory_enricher_dev36 import _compact_human_cause
from targeted_memory_enricher_dev68 import TargetedMemoryEnricher as Dev68TargetedMemoryEnricher
from trace_action_local_dev68 import (
    select_completed_wait_cause,
    select_elapsed_delay_cause,
    select_trigger_with_true_conditions,
)
from trace_branch_path_dev70 import select_executed_branch_conditions
from trace_final_action_dev63 import select_chosen_branch_conditions, select_wait_timeout_cause
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text


class TargetedMemoryEnricher(Dev68TargetedMemoryEnricher):
    """dev.70: preserve dev.68, add one structural branch-path proof before fallback."""

    def _combine_trigger_and_branch(
        self,
        trigger: dict[str, Any] | None,
        branch: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(trigger, dict) or not isinstance(branch, dict):
            return None
        conditions = branch.get("detail", {}).get("conditions") if isinstance(branch.get("detail"), dict) else None
        if not isinstance(conditions, list) or not conditions:
            return None
        platform = str(trigger.get("platform") or trigger.get("trigger") or "").casefold()
        if platform not in {"state", "numeric_state"}:
            return None
        return {
            "kind": "required_conditions",
            "origin": "trigger_plus_conditions",
            "path": "trigger+executed-branch",
            "command_path": branch.get("command_path"),
            "proven": True,
            "detail": {
                "trigger": dict(trigger),
                "conditions": list(conditions),
            },
            "effect_command": branch.get("effect_command"),
        }

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

        # Keep the proven dev.68 order. The only addition is a structural branch-path
        # selector immediately before the old branch/start-trigger fallbacks.
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
            branch = select_executed_branch_conditions(result)
            if isinstance(branch, dict):
                trigger = _proven_start_trigger(result)
                platform = str((trigger or {}).get("platform") or (trigger or {}).get("trigger") or "").casefold()
                if platform == "time_pattern":
                    human_cause = branch
                else:
                    human_cause = self._combine_trigger_and_branch(trigger, branch) or branch

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
        elif origin in {"choose_conditions", "executed_branch_conditions"}:
            text = await self._conjunction_text(human_cause)
        elif origin == "trigger_plus_conditions":
            text = await self._trigger_conditions_text(human_cause)
        else:
            await self._label_cause(human_cause)
            text = human_cause_text(human_cause) if human_cause else None

        return text, run_id, _compact_human_cause(human_cause)
