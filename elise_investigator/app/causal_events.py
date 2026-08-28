from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


# Generic Home Assistant control attributes worth treating as user-visible
# changes even when the entity's primary state remains unchanged. This list is
# intentionally domain-based: no Maison Cognitive entity id belongs here.
CONTROL_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "cover": ("current_position", "current_tilt_position"),
    "light": ("brightness",),
    "fan": ("percentage", "preset_mode"),
    "climate": ("temperature", "target_temp_high", "target_temp_low", "preset_mode", "fan_mode"),
    "humidifier": ("humidity", "mode"),
    "media_player": ("volume_level", "source"),
    "vacuum": ("fan_speed",),
    "water_heater": ("temperature", "operation_mode"),
}


@dataclass(slots=True)
class ObservedChange:
    entity_id: str
    entity_name: str | None
    event_time: str
    event_kind: str
    before_value: Any
    after_value: Any
    attribute: str | None
    context_id: str | None
    parent_id: str | None
    user_id: str | None
    domain: str


def _utc_iso(value: str | None) -> str:
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


def _event_kind(domain: str, after: Any, attribute: str | None) -> str:
    if attribute == "current_position":
        return "positioned"
    if attribute == "current_tilt_position":
        return "tilt_positioned"
    if attribute == "brightness":
        return "brightness_changed"
    if attribute == "percentage":
        return "percentage_changed"
    if attribute in {"temperature", "target_temp_high", "target_temp_low"}:
        return "target_temperature_changed"
    if attribute == "volume_level":
        return "volume_changed"
    if attribute in {"source", "preset_mode", "fan_mode", "mode", "operation_mode", "fan_speed"}:
        return f"{attribute}_changed"

    value = str(after).lower() if after is not None else ""
    if domain in {"light", "switch", "input_boolean", "fan", "humidifier"}:
        if value == "on":
            return "turned_on"
        if value == "off":
            return "turned_off"
    if domain == "cover":
        return {
            "opening": "opening",
            "closing": "closing",
            "open": "opened",
            "closed": "closed",
        }.get(value, "state_changed")
    if domain == "lock":
        return {"locked": "locked", "unlocked": "unlocked"}.get(value, "state_changed")
    if domain == "climate":
        return "hvac_mode_changed"
    return "state_changed"


def _context(event: dict[str, Any], new_state: dict[str, Any]) -> dict[str, Any]:
    raw = new_state.get("context")
    if not isinstance(raw, dict):
        raw = event.get("context")
    return raw if isinstance(raw, dict) else {}


def changes_from_state_event(event: dict[str, Any]) -> list[ObservedChange]:
    """Return meaningful state/control-attribute changes from one HA event.

    Entity creation/removal and attribute-only bookkeeping updates are ignored.
    A single event can legitimately yield both a primary-state change and a
    relevant control-attribute change. Later recorder logic may coalesce those
    into one causal episode when they share the same proof.
    """

    if not isinstance(event, dict) or event.get("event_type") != "state_changed":
        return []
    data = event.get("data")
    if not isinstance(data, dict):
        return []
    entity_id = str(data.get("entity_id") or "").strip()
    if "." not in entity_id:
        return []
    old_state = data.get("old_state")
    new_state = data.get("new_state")
    if not isinstance(old_state, dict) or not isinstance(new_state, dict):
        return []

    domain = entity_id.split(".", 1)[0]
    old_value = old_state.get("state")
    new_value = new_state.get("state")
    old_attrs = old_state.get("attributes") if isinstance(old_state.get("attributes"), dict) else {}
    new_attrs = new_state.get("attributes") if isinstance(new_state.get("attributes"), dict) else {}
    ctx = _context(event, new_state)
    event_time = _utc_iso(event.get("time_fired") or new_state.get("last_updated"))
    entity_name = new_attrs.get("friendly_name") or old_attrs.get("friendly_name")

    def make(before: Any, after: Any, attribute: str | None) -> ObservedChange:
        return ObservedChange(
            entity_id=entity_id,
            entity_name=str(entity_name) if entity_name is not None else None,
            event_time=event_time,
            event_kind=_event_kind(domain, after, attribute),
            before_value=before,
            after_value=after,
            attribute=attribute,
            context_id=str(ctx.get("id")) if ctx.get("id") is not None else None,
            parent_id=str(ctx.get("parent_id")) if ctx.get("parent_id") is not None else None,
            user_id=str(ctx.get("user_id")) if ctx.get("user_id") is not None else None,
            domain=domain,
        )

    changes: list[ObservedChange] = []
    if old_value != new_value:
        changes.append(make(old_value, new_value, None))

    for attribute in CONTROL_ATTRIBUTES.get(domain, ()):
        before = old_attrs.get(attribute)
        after = new_attrs.get(attribute)
        if before != after and (before is not None or after is not None):
            changes.append(make(before, after, attribute))

    return changes
