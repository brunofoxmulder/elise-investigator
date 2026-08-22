from __future__ import annotations

from datetime import datetime
from typing import Any

from investigator import Investigator, _extract_service_actions
from models import InvestigationRequest, InvestigationResult

VERSION = "0.1.0-beta.10"


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


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _is_window_boundary_artifact(
    result: InvestigationResult,
    request: InvestigationRequest | None,
) -> bool:
    """Detect Recorder's boundary state being mistaken for a state transition.

    Home Assistant History may return the state already active at the exact beginning of
    the requested period. When no explicit observed time was supplied, a lone boundary
    row has no previous row and must not be presented as ``None -> state``.
    """
    if request is None or request.observed_time:
        return False
    if result.event_type != "state_change" or result.observed.get("before") is not None:
        return False

    event_time = _dt(result.event_time)
    window_start = _dt((result.meta.get("window") or {}).get("start"))
    if event_time is None or window_start is None:
        return False
    if abs((event_time - window_start).total_seconds()) > 1.0:
        return False

    history = next((item for item in result.evidence if item.kind == "history"), None)
    if history is None or not isinstance(history.raw, dict):
        return False
    return history.raw.get("previous") is None


def _apply_window_boundary_policy(result: InvestigationResult) -> None:
    """Turn a History boundary row into an honest 'state already active' result."""
    label = result.entity_name or result.entity_id
    after = result.observed.get("after")
    boundary_time = result.event_time

    result.status = "indeterminate"
    result.event_type = "window_boundary_state"
    result.event_time = None
    result.observed["description"] = (
        f"{label} était déjà dans l'état {after} au début de la période examinée ; "
        "aucun changement d'état n'est prouvé à cet instant."
    )
    result.cause = {
        "type": "unknown",
        "entity_id": None,
        "name": None,
        "system_confirmed": False,
    }
    result.chain = []
    # Reverse-search candidates and nearby trace/logbook evidence were computed around a
    # timestamp that is not an event. Keeping them would invite false causal attribution.
    result.candidates = []

    kept_evidence = []
    for evidence in result.evidence:
        if evidence.kind == "history":
            evidence.summary = (
                f"État de bord Recorder : {after} au début de la fenêtre ; "
                "aucune transition précédente n'est disponible."
            )
            evidence.strength = "supporting"
            kept_evidence.append(evidence)
        elif evidence.kind == "user_declaration":
            kept_evidence.append(evidence)
    result.evidence = kept_evidence

    result.limits = [
        "L'état retourné au début de la fenêtre est un état de bord du Recorder, pas une transition prouvée.",
        "Le dernier changement d'état n'a pas été retrouvé dans la période examinée.",
    ]
    result.meta["boundary_state"] = {
        "timestamp": boundary_time,
        "state": after,
    }


def enforce_result_policy(
    result: InvestigationResult,
    request: InvestigationRequest | None = None,
) -> InvestigationResult:
    """Apply conservative proof semantics to a completed investigation result."""
    if _is_window_boundary_artifact(result, request):
        _apply_window_boundary_policy(result)

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
    rules["window_boundary_is_not_event"] = True
    return result


class StrictInvestigator(Investigator):
    """Investigator with conservative causal-proof policies."""

    async def _reverse_search(self, entity_id: str, event_time):
        candidates = await super()._reverse_search(entity_id, event_time)
        for candidate in candidates:
            # Re-evaluate the legacy flag using executed trace nodes only. This prevents a
            # target appearing merely in stored automation configuration from being treated
            # as proof of execution.
            candidate.target_proven = bool(executed_trace_actions(candidate.trace, entity_id))
        return candidates

    def _build_answer(self, result: InvestigationResult) -> str:
        if result.event_type == "window_boundary_state":
            event_sentence = result.observed.get("description") or "État de bord observé."
            return (
                f"Cause indéterminée. {event_sentence} "
                "Le dernier changement d'état n'a pas été retrouvé ; aucune cause ne peut être attribuée."
            ).strip()
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
        enforce_result_policy(result, request=request)
        # The base engine builds answer_text before the policy is applied.
        result.answer_text = self._build_answer(result)
        return result
