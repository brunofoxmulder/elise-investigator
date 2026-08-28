from __future__ import annotations

from models import InvestigationResult


def _event_sentence(result: InvestigationResult) -> str:
    text = str(result.observed.get("description") or "").strip()
    if not text:
        return ""
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _has_limit(result: InvestigationResult, fragment: str) -> bool:
    needle = fragment.casefold()
    return any(needle in str(item).casefold() for item in result.limits)


def build_indeterminate_explanation(result: InvestigationResult) -> str | None:
    """Explain why causal proof is insufficient without inventing a cause."""
    if result.status != "indeterminate":
        return None

    event = _event_sentence(result)
    prefix = "Cause indéterminée."

    if result.event_type == "window_boundary_state":
        return (
            f"{prefix} {event} Le Recorder montre seulement l'état déjà présent au début de la période ; "
            "le changement précédent n'est pas dans les preuves examinées."
        ).strip()

    if result.cause.get("type") == "multiple_candidates":
        return (
            f"{prefix} {event} Plusieurs exécutions ont réellement ciblé cet objet, mais les preuves "
            "conservées ne permettent pas de savoir laquelle a provoqué ce changement."
        ).strip()

    if result.event_type == "current_state_only" or _has_limit(
        result, "aucun événement historique correspondant"
    ):
        label = result.entity_name or result.entity_id
        return (
            f"{prefix} Je vois l'état actuel de {label}, mais le changement qui l'a produit n'est pas "
            "présent dans la fenêtre étudiée. Je ne peux donc pas attribuer de cause."
        )

    enabled_candidates = [
        item for item in result.candidates if item.get("enabled_now") is not False
    ]
    if len(enabled_candidates) > 1:
        return (
            f"{prefix} {event} Plusieurs automatisations ou scripts peuvent agir sur cet objet, mais "
            "aucune exécution précise n'est reliée à ce changement dans les preuves conservées."
        ).strip()

    if any(item.kind == "history" for item in result.evidence):
        return (
            f"{prefix} {event} Le changement est bien enregistré dans l'historique, mais aucun contexte "
            "Home Assistant ni aucune trace d'exécution ne le relie à une cause."
        ).strip()

    if result.limits:
        return f"{prefix} {event} Limite : {result.limits[0]}".strip()

    return (
        f"{prefix} {event} Les preuves disponibles ne permettent pas d'établir une cause sans faire "
        "d'hypothèse."
    ).strip()
