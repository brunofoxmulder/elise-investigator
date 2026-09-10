from __future__ import annotations

from typing import Any

from action_effect_cause import select_effect_linked_cause
from causal_recorder import CausalRecord
from human_cause import _proven_start_trigger, select_human_cause
from models import Evidence, InvestigationResult
from proof_policy import executed_trace_actions
from targeted_memory_enricher_dev36 import _compact_human_cause
from targeted_memory_enricher_dev70 import TargetedMemoryEnricher as Dev70TargetedMemoryEnricher
from trace_action_local_dev68 import (
    select_completed_wait_cause,
    select_elapsed_delay_cause,
    select_trigger_with_true_conditions,
)
from trace_action_local_dev71 import select_adjacent_temporal_cause
from trace_branch_path_dev70 import select_executed_branch_conditions
from trace_final_action_dev63 import select_wait_timeout_cause
from trigger_semantics import complete_confirmed_trace_chain, human_cause_text


class TargetedMemoryEnricher(Dev70TargetedMemoryEnricher):
    """dev.71: keep dev.70 evidence, but enforce cause/guard/temporal semantics."""

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

        # Strong, action-local causes first.
        human_cause = select_effect_linked_cause(result)
        if human_cause is None:
            human_cause = select_completed_wait_cause(result)
        if human_cause is None:
            human_cause = select_wait_timeout_cause(result)
        if human_cause is None:
            human_cause = select_elapsed_delay_cause(result)
        if human_cause is None:
            human_cause = select_adjacent_temporal_cause(result)

        # Top-level trigger + conditions is allowed only as a conjunction rooted in a
        # real state/numeric-state trigger. Conditions alone are guards, not causes.
        if human_cause is None:
            combined = select_trigger_with_true_conditions(result)
            trigger = _proven_start_trigger(result)
            platform = str((trigger or {}).get("platform") or (trigger or {}).get("trigger") or "").casefold()
            if combined is not None and platform in {"state", "numeric_state"}:
                human_cause = combined

        # Nested branch conditions may enrich a proven state/numeric-state trigger,
        # but are never promoted to a standalone cause (fixes dev.70 time_pattern case).
        if human_cause is None:
            branch = select_executed_branch_conditions(result)
            trigger = _proven_start_trigger(result)
            platform = str((trigger or {}).get("platform") or (trigger or {}).get("trigger") or "").casefold()
            if isinstance(branch, dict) and platform in {"state", "numeric_state"}:
                human_cause = self._combine_trigger_and_branch(trigger, branch)

        # Generic start-trigger fallback is permitted only when no action-local temporal
        # release exists. If a delay/wait released the target, the initial trigger must
        # not be reused as the cause of that later action.
        if human_cause is None and select_adjacent_temporal_cause(result) is None:
            candidate = select_human_cause(result)
            if isinstance(candidate, dict):
                origin = candidate.get("origin")
                if origin != "automation_trigger" or not self._has_any_executed_temporal_barrier(result):
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

    @staticmethod
    def _has_any_executed_temporal_barrier(result: InvestigationResult) -> bool:
        """Fail closed against a stale automation-start trigger after an executed delay/wait.

        This intentionally does not claim that every temporal action caused the target;
        it only blocks the unsafe fallback to the initial trigger when the trace proves
        that execution crossed a temporal boundary somewhere before completion.
        """
        detail = next(
            (
                evidence.raw
                for evidence in result.evidence
                if evidence.kind == "trace" and isinstance(evidence.raw, dict)
            ),
            None,
        )
        if not isinstance(detail, dict):
            return False
        config = detail.get("config")
        trace = detail.get("trace")
        if not isinstance(config, dict) or not isinstance(trace, dict):
            return False

        def walk(value: Any, path: str = "") -> bool:
            if isinstance(value, dict):
                if ("delay" in value or "wait_for_trigger" in value) and path and trace.get(path):
                    return True
                for key in ("actions", "action", "sequence"):
                    items = value.get(key)
                    if isinstance(items, list):
                        prefix = "action" if key in {"actions", "action"} and not path else "sequence"
                        for index, item in enumerate(items):
                            child = f"{path}/{prefix}/{index}" if path else f"{prefix}/{index}"
                            if walk(item, child):
                                return True
                choices = value.get("choose")
                if isinstance(choices, list):
                    for index, choice in enumerate(choices):
                        child = f"{path}/choose/{index}" if path else f"choose/{index}"
                        if walk(choice, child):
                            return True
            return False

        return walk(config)
