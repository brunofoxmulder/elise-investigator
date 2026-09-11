from __future__ import annotations

from typing import Any

from causal_utils import duration_text
from trigger_semantics import human_cause_text


class CausalRendererV2:
    """Single semantic renderer for one already-proven causal object."""

    def __init__(self, ha):
        self.ha = ha

    async def _label(self, cause: dict[str, Any] | None) -> None:
        if not isinstance(cause, dict):
            return
        detail = cause.get("detail")
        entity_id = str(detail.get("entity_id") or "") if isinstance(detail, dict) else ""
        if not entity_id:
            return
        try:
            state = await self.ha.get_state(entity_id)
        except Exception:
            return
        if not isinstance(state, dict):
            return
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        if attrs.get("friendly_name"):
            cause["entity_name"] = str(attrs["friendly_name"])
        if attrs.get("device_class"):
            cause["device_class"] = str(attrs["device_class"])
        if attrs.get("unit_of_measurement"):
            cause["unit"] = str(attrs["unit_of_measurement"])

    @staticmethod
    def _time_pattern_text(detail: dict[str, Any]) -> str:
        for key, unit in (("seconds", "secondes"), ("minutes", "minutes"), ("hours", "heures")):
            value = detail.get(key)
            text = str(value or "").strip()
            if text.startswith("/"):
                try:
                    number = int(text[1:])
                except ValueError:
                    continue
                if number > 0:
                    singular = {"secondes": "seconde", "minutes": "minute", "heures": "heure"}[unit]
                    label = singular if number == 1 else unit
                    return f"le contrôle périodique toutes les {number} {label} s'est déclenché"
        return "le contrôle périodique prévu s'est déclenché"

    async def _atom_text(self, cause: dict[str, Any]) -> str | None:
        detail = cause.get("detail")
        if not isinstance(detail, dict):
            return None
        platform = str(detail.get("platform") or detail.get("trigger") or "").casefold()
        if platform == "time_pattern":
            return self._time_pattern_text(detail)
        await self._label(cause)
        return human_cause_text(cause)

    async def render(self, cause: dict[str, Any] | None) -> str | None:
        if not isinstance(cause, dict):
            return None
        origin = str(cause.get("origin") or "")
        detail = cause.get("detail") if isinstance(cause.get("detail"), dict) else {}

        if origin == "wait_timeout":
            duration = detail.get("duration_text")
            if duration:
                return f"la durée maximale de {duration} a été atteinte"
        if origin == "delay_elapsed":
            duration = detail.get("duration_text")
            if not duration and detail.get("delay_seconds") is not None:
                duration = duration_text(detail.get("delay_seconds"))
            if duration:
                return f"le délai de {duration} s'est écoulé"

        if origin == "trigger_plus_conditions":
            trigger = detail.get("trigger")
            conditions = detail.get("conditions")
            if not isinstance(trigger, dict) or not isinstance(conditions, list) or not conditions:
                return None
            atoms: list[dict[str, Any]] = [
                {
                    "kind": "automation_trigger",
                    "origin": "automation_trigger",
                    "proven": True,
                    "detail": dict(trigger),
                }
            ]
            atoms.extend(
                {
                    "kind": "required_condition",
                    "origin": "required_condition",
                    "proven": True,
                    "detail": dict(item),
                }
                for item in conditions
                if isinstance(item, dict)
            )
            if len(atoms) != len(conditions) + 1:
                return None
            texts: list[str] = []
            for atom in atoms:
                text = await self._atom_text(atom)
                if not text:
                    return None
                texts.append(text.rstrip("."))
            if len(texts) == 2:
                return f"{texts[0]} et {texts[1]}"
            return ", ".join(texts[:-1]) + f" et {texts[-1]}"

        return await self._atom_text(cause)
