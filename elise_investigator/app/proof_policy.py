from __future__ import annotations

from typing import Any

from investigator import Investigator, _extract_service_actions
from models import InvestigationRequest, InvestigationResult

VERSION = "0.1.0-beta.8"


def executed_trace_actions(detail: dict[str, Any] | None, target_entity: str) -> list[dict[str, Any]]:
    """Return only service actions found in executed trace nodes.

    Home Assistant trace payloads can also contain the automation configuration. A mere
    mention of an entity in that configuration is not proof that the corresponding action
    was executed for the investigated event. We therefore inspect the runtime ``trace``
    tree only.
    """
    if not isinstance(detail, dict):
        return []
    trace_nodes = detail.get("trace")
    if not isinstance(trace_nodes, dict):
        return []
    return _extract_service_actions(trace_nodes, target_entity)


def enforce_result_policy(result: InvestigationResult) -> InvestigationResult:
    """Apply conservative proof semantics to a completed investigation result."""
    if result.cause.get("type") == "multiple":
        sources = [str(source) for source in result.cause.get("sources") or []]
        result.status = "indeterminate"
        result.cause = {
            "type": "multiple_candidates",
            "entity_id": None,
            "name": "Plusieurs exécutions candidates",
            "system_confirmed": False,
            "exclusive": False,
            "sources": sources,
        }

        # The executions themselves are evidenced, but attribution of the observed state
        # change to one of them is not. Keep the evidence while downgrading its causal
        # strength.
        for evidence in result.evidence:
            if evidence.kind == "trace" and evidence.source in sources:
                evidence.strength = "supporting"
                evidence.summary = (
                    f"Exécution proche de l'événement avec action vers {result.entity_id}; "
                    "l'attribution causale reste ambiguë"
                )

        result.limits = [
            item
            for item in result.limits
            if "Plusieurs causes peuvent être vraies simultanément" not in item
        ]
        result.limits.append(
            "Plusieurs exécutions proches ont réellement ciblé l'entité ; les preuves conservées "
            "ne permettent pas d'attribuer ce changement à une cause unique."
        )

    result.meta["version"] = VERSION
    rules = result.meta.setdefault("rules", {})
    rules["multiple_traces_do_not_prove_unique_cause"] = True
    rules["config_mention_is_not_executed_action"] = True
    return result


class StrictInvestigator(Investigator):
    """Investigator with the conservative causal-proof policy introduced in beta.7."""

    async def _reverse_search(self, entity_id: str, event_time):
        candidates = await super()._reverse_search(entity_id, event_time)
        for candidate in candidates:
            # Re-evaluate the legacy flag using executed trace nodes only. This prevents a
            # target appearing merely in stored automation configuration from being treated
            # as proof of execution.
            candidate.target_proven = bool(executed_trace_actions(candidate.trace, entity_id))
        return candidates

    def _build_answer(self, result: InvestigationResult) -> str:
        if result.cause.get("type") == "multiple_candidates":
            event_sentence = result.observed.get("description") or "Événement observé."
            limit = f" Limite : {result.limits[0]}" if result.limits else ""
            return (
                f"Cause indéterminée. {event_sentence} Plusieurs exécutions proches ont réellement "
                f"ciblé cette entité, mais aucune ne peut être attribuée comme cause unique.{limit}"
            ).strip()
        return super()._build_answer(result)

    async def investigate(self, request: InvestigationRequest) -> InvestigationResult:
        result = await super().investigate(request)
        enforce_result_policy(result)
        # The base engine builds answer_text before the policy is applied.
        result.answer_text = self._build_answer(result)
        return result
