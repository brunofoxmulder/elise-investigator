from __future__ import annotations

import unicodedata
from typing import Any

from models import InvestigationResult


def nodes(value: Any) -> list[dict[str, Any]]:
    """Return dict trace nodes from Home Assistant's one-or-many node shapes."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return [value] if isinstance(value, dict) else []


def walk_contains(obj: Any, needle: str) -> bool:
    """Recursively test whether a runtime payload references a target string."""
    if isinstance(obj, str):
        return needle in obj
    if isinstance(obj, dict):
        return any(walk_contains(key, needle) or walk_contains(value, needle) for key, value in obj.items())
    if isinstance(obj, (list, tuple)):
        return any(walk_contains(value, needle) for value in obj)
    return False


def trace_detail(result: InvestigationResult) -> dict[str, Any] | None:
    """Return direct trace evidence for the already-selected source only."""
    source = result.cause.get("entity_id")
    for evidence in result.evidence:
        if evidence.kind != "trace" or not isinstance(evidence.raw, dict):
            continue
        if source and evidence.source and evidence.source != source:
            continue
        return evidence.raw
    return None


def state_attributes(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    attrs = state.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def state_value(state: Any) -> Any:
    return state.get("state") if isinstance(state, dict) else None


def normalize_text(value: Any) -> str:
    """Case/diacritic-insensitive text used only for semantic label matching."""
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").casefold()


def friendly_name(cause: dict[str, Any]) -> str:
    if cause.get("entity_name"):
        return str(cause["entity_name"])
    detail = cause.get("detail")
    if isinstance(detail, dict):
        for key in ("to_state", "from_state"):
            name = state_attributes(detail.get(key)).get("friendly_name")
            if name:
                return str(name)
        entity_id = str(detail.get("entity_id") or "")
        if "." in entity_id:
            entity_id = entity_id.split(".", 1)[1]
        if entity_id:
            return entity_id.replace("_", " ")
    return "le déclencheur"


def device_class(cause: dict[str, Any]) -> str:
    if cause.get("device_class"):
        return str(cause["device_class"])
    detail = cause.get("detail")
    if isinstance(detail, dict):
        for key in ("to_state", "from_state"):
            value = state_attributes(detail.get(key)).get("device_class")
            if value:
                return str(value)
    return ""


def unit(cause: dict[str, Any]) -> str:
    if cause.get("unit"):
        return str(cause["unit"])
    detail = cause.get("detail")
    if isinstance(detail, dict):
        for key in ("to_state", "from_state"):
            value = state_attributes(detail.get(key)).get("unit_of_measurement")
            if value:
                return str(value)
    return ""


def number_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return (f"{number:.3f}").rstrip("0").rstrip(".").replace(".", ",")


def duration_seconds(value: Any) -> float | None:
    """Normalize HA duration shapes, including serialized timedeltas and signed HH:MM:SS."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        if value.get("total_seconds") is not None:
            try:
                return float(value["total_seconds"])
            except (TypeError, ValueError):
                return None
        try:
            return (
                float(value.get("hours", 0)) * 3600
                + float(value.get("minutes", 0)) * 60
                + float(value.get("seconds", 0))
            )
        except (TypeError, ValueError):
            return None

    text = str(value).strip()
    sign = -1 if text.startswith("-") else 1
    if text[:1] in {"+", "-"}:
        text = text[1:]
    parts = text.split(":")
    if len(parts) == 3:
        try:
            hours, minutes, seconds = (float(part) for part in parts)
            return sign * (hours * 3600 + minutes * 60 + seconds)
        except ValueError:
            return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def duration_text(seconds: float | None) -> str | None:
    if seconds is None or seconds <= 0:
        return None
    rounded = int(round(seconds))
    if rounded % 3600 == 0:
        hours = rounded // 3600
        return f"{hours} heure" if hours == 1 else f"{hours} heures"
    if rounded % 60 == 0:
        minutes = rounded // 60
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    return f"{rounded} secondes"
