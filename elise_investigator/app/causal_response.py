from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecord


def _number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return (f"{number:.2f}").rstrip("0").rstrip(".").replace(".", ",")


def _effect(record: CausalRecord) -> str:
    label = record.entity_name or record.entity_id
    domain = record.entity_id.split(".", 1)[0]
    value = record.after_value

    if record.event_kind == "positioned":
        return f"{label} a été positionné à {_number(value)} %"
    if record.event_kind == "tilt_positioned":
        return f"L'inclinaison de {label} a été réglée à {_number(value)} %"
    if record.event_kind == "brightness_changed":
        return f"La luminosité de {label} a changé"
    if record.event_kind == "target_temperature_changed":
        return f"La consigne de {label} est passée à {_number(value)}"
    if record.event_kind == "hvac_mode_changed":
        return f"{label} est passé en mode {value}"
    if domain == "light" and record.event_kind == "turned_on":
        return f"{label} s'est allumée"
    if domain == "light" and record.event_kind == "turned_off":
        return f"{label} s'est éteinte"
    if record.event_kind == "turned_on":
        return f"{label} s'est activé"
    if record.event_kind == "turned_off":
        return f"{label} s'est désactivé"
    if domain == "cover" and record.event_kind == "opened":
        return f"{label} s'est ouvert"
    if domain == "cover" and record.event_kind == "closed":
        return f"{label} s'est fermé"
    if domain == "cover" and record.event_kind == "opening":
        return f"{label} a commencé à s'ouvrir"
    if domain == "cover" and record.event_kind == "closing":
        return f"{label} a commencé à se fermer"
    if record.event_kind == "locked":
        return f"{label} s'est verrouillé"
    if record.event_kind == "unlocked":
        return f"{label} s'est déverrouillé"
    if value is not None:
        return f"{label} est passé à {value}"
    return f"Un changement de {label} a été enregistré"


def _because(reason: str) -> str:
    text = reason.strip().rstrip(".")
    if not text:
        return ""
    if text[0].lower() in "aeiouyh":
        return f"parce qu'{text}"
    return f"parce que {text}"


def answer_from_record(record: CausalRecord) -> str:
    """Render only the facts stored by the deterministic journal."""
    effect = _effect(record).rstrip(".")

    if record.origin_type in {"automation", "script"} and record.reason:
        reason = _because(record.reason)
        if record.confidence == "confirmed":
            return f"{effect} {reason}."
        if record.confidence == "probable":
            return f"{effect}. Cause probable : {record.reason.rstrip('.')} .".replace(" .", ".")

    if record.origin_type == "alexa" and record.confidence == "confirmed":
        return f"{effect} à la suite d'une commande Alexa."
    if record.origin_type == "user" and record.confidence == "confirmed":
        return f"{effect} à la suite d'une commande utilisateur Home Assistant."

    if record.origin_type in {"automation", "script"} and record.confidence == "confirmed":
        return (
            f"{effect}. Le journal confirme qu'une automatisation ou un script a provoqué ce changement, "
            "mais la raison fonctionnelle n'a pas pu être isolée avec certitude."
        )

    if record.confidence == "probable" and record.reason:
        return f"{effect}. Cause probable : {record.reason.rstrip('.')} .".replace(" .", ".")

    return f"{effect}. Le changement est enregistré, mais sa cause n'est pas établie."
