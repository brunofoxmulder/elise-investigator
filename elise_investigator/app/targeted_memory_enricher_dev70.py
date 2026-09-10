from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecord
from models import Evidence, InvestigationResult
from proof_policy import executed_trace_actions
from targeted_memory_enricher_dev36 import _compact_human_cause
from targeted_memory_enricher_dev68 import TargetedMemoryEnricher as Dev68TargetedMemoryEnricher
from trace_branch_path_dev70 import select_executed_branch_conditions
from trigger_semantics import complete_confirmed_trace_chain


class TargetedMemoryEnricher(Dev68TargetedMemoryEnricher):
    """dev.70: only replace a technical/partial trigger fallback with exact branch proof."""

    async def _reason_from_detail(
        self,
        record: CausalRecord,
        source_entity_id: str,
        source_name: str | None,
        source_kind: str,
        detail: dict[str, Any],
        run_id: str | None,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        text, run_id, cause = await super()._reason_from_detail(
            record,
            source_entity_id,
            source_name,
            source_kind,
            detail,
            run_id,
        )

        if not executed_trace_actions(detail, record.entity_id):
            return text, run_id, cause
        if not isinstance(cause, dict) or cause.get("origin") != "automation_trigger":
            return text, run_id, cause

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
        branch = select_executed_branch_conditions(result)
        if not isinstance(branch, dict):
            return text, run_id, cause

        branch_text = await self._conjunction_text(branch)
        if not branch_text:
            return text, run_id, cause

        trigger_detail = cause.get("detail") if isinstance(cause.get("detail"), dict) else {}
        platform = str(trigger_detail.get("platform") or "").casefold()

        # time_pattern is only scheduler provenance: exact branch conditions are more
        # functional when HA proves them on the path to the target action.
        if platform == "time_pattern":
            branch["origin"] = "executed_branch_conditions"
            return branch_text, run_id, _compact_human_cause(branch)

        # For a state/numeric trigger plus a proven branch condition, both may be
        # jointly required (e.g. off-peak started AND battery was low). Preserve both.
        if platform in {"state", "numeric_state"}:
            combined = {
                "kind": "required_conditions",
                "origin": "trigger_plus_conditions",
                "path": "trigger+executed-branch",
                "command_path": branch.get("command_path"),
                "proven": True,
                "detail": {
                    "trigger": dict(trigger_detail),
                    "conditions": list(branch.get("detail", {}).get("conditions") or []),
                },
                "effect_command": branch.get("effect_command"),
            }
            combined_text = await self._trigger_conditions_text(combined)
            if combined_text:
                return combined_text, run_id, _compact_human_cause(combined)

        return text, run_id, cause
