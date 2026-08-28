from __future__ import annotations

from datetime import datetime, timezone
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


def _when(event_time: str, now: datetime | None = None) -> str:
    try:
        event = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        if event.tzinfo is None:
            event = event.replace(tzinfo=timezone.utc)
        event = event.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return ""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    seconds = max(0, int((current.astimezone(timezone.utc) - event).total_seconds()))
    if seconds < 45:
        return "à l'instant"
    if seconds < 90:
        return "il y a 1 minute"
    if seconds < 3600:
        return f"il y a {round(seconds / 60)} minutes"
    if seconds < 5400:
        return "il y a 1 heure"
    if seconds < 43200:
        return f"il y a {round(seconds / 3600)} heures"
    return ""


def cause_found(record: CausalRecord) -> bool:
    if record.origin_type in {"user", "alexa"}:
        return True
    return bool(record.origin_type in {"automation", "script"} and record.reason)


def answer_from_memory(record: CausalRecord, *, now: datetime | None = None) -> str:
    """Render the dev.34 memory without any certainty evaluation."""

    if not cause_found(record):
        return "Je n'ai pas trouvé la cause."

    effect = _effect(record).rstrip(".")
    when = _when(record.event_time, now=now)
    suffix = f" {when}" if when else ""

    if record.origin_type in {"automation", "script"} and record.reason:
        return f"{effect} {_because(record.reason)}{suffix}."
    if record.origin_type == "alexa":
        return f"{effect} à la suite d'une commande Alexa{suffix}."
    if record.origin_type == "user":
        return f"{effect} à la suite d'une commande utilisateur{suffix}."

    return "Je n'ai pas trouvé la cause."
