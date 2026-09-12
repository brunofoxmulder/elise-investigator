from __future__ import annotations

from typing import Any

from causal_utils import duration_text, number_text
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

    async def _factor_text(self, factor: dict[str, Any]) -> str | None:
        kind = str(factor.get("kind") or "")
        entity_id = factor.get("proof_entity_id")
        if not entity_id:
            return None
        detail: dict[str, Any] = {"platform": kind, "entity_id": entity_id}
        if kind == "state":
            detail["to"] = factor.get("value")
        elif kind == "numeric_state":
            relation = str(factor.get("relation") or "")
            if relation == "above":
                detail["above"] = factor.get("threshold")
            elif relation == "below":
                detail["below"] = factor.get("threshold")
            else:
                return None
            if factor.get("value") is not None:
                detail["actual"] = factor.get("value")
        else:
            return None
        return await self._atom_text(
            {
                "kind": "required_factor",
                "origin": "required_factor",
                "proven": True,
                "detail": detail,
            }
        )

    async def _factors_text(self, factors: list[dict[str, Any]]) -> str | None:
        texts: list[str] = []
        for factor in factors:
            if not isinstance(factor, dict):
                return None
            text = await self._factor_text(factor)
            if not text:
                return None
            texts.append(text.rstrip("."))
        if len(texts) < 2:
            return texts[0] if texts else None
        if len(texts) == 2:
            return f"{texts[0]} et {texts[1]}"
        return ", ".join(texts[:-1]) + f" et {texts[-1]}"

    @staticmethod
    def _solar_attribute_text(detail: dict[str, Any]) -> str | None:
        attribute = str(detail.get("attribute") or "").casefold()
        if attribute not in {"azimuth", "elevation"}:
            return None
        subject = "l’azimut solaire" if attribute == "azimuth" else "l’élévation solaire"
        above = detail.get("above")
        below = detail.get("below")
        if above is not None and below is not None:
            return (
                f"{subject} était compris entre {number_text(above)}° et "
                f"{number_text(below)}°"
            )
        if above is not None:
            return f"{subject} dépassait {number_text(above)}°"
        if below is not None:
            return f"{subject} était inférieur à {number_text(below)}°"
        return None

    async def _cover_condition_text(self, condition: dict[str, Any]) -> str | None:
        if not isinstance(condition, dict):
            return None
        if str(condition.get("platform") or "").casefold() != "numeric_state":
            return None
        solar = self._solar_attribute_text(condition)
        if solar:
            return solar
        atom = {
            "kind": "cover_decision_factor",
            "origin": "cover_decision_factor",
            "proven": True,
            "detail": dict(condition),
        }
        return await self._atom_text(atom)

    async def _cover_conditions_text(self, conditions: list[dict[str, Any]]) -> str | None:
        texts: list[str] = []
        for condition in conditions:
            text = await self._cover_condition_text(condition)
            if text:
                texts.append(text.rstrip("."))
        if not texts:
            return None
        if len(texts) == 1:
            return texts[0]
        if len(texts) == 2:
            return f"{texts[0]} et {texts[1]}"
        return ", ".join(texts[:-1]) + f" et {texts[-1]}"

    @staticmethod
    def _runtime_inputs_text(inputs: dict[str, Any]) -> str | None:
        """Render an evidence-only snapshot of a computed cover decision."""
        parts: list[str] = []
        if inputs.get("temperature") is not None:
            parts.append(f"température {number_text(inputs['temperature'])} °C")
        if inputs.get("azimuth") is not None:
            parts.append(f"azimut {number_text(inputs['azimuth'])}°")
        if inputs.get("elevation") is not None:
            parts.append(f"élévation {number_text(inputs['elevation'])}°")
        if inputs.get("lux") is not None:
            parts.append(f"luminosité {number_text(inputs['lux'])} lx")
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} et {parts[1]}"
        return ", ".join(parts[:-1]) + f" et {parts[-1]}"

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

        if origin == "cover_periodic_position":
            trigger = detail.get("trigger")
            position = detail.get("requested_position")
            factors = detail.get("decision_factors")
            runtime_inputs = detail.get("runtime_inputs")
            if isinstance(trigger, dict) and position is not None:
                trigger_text = self._time_pattern_text(trigger).rstrip(".")
                try:
                    numeric = float(position)
                    position_text = str(int(numeric)) if numeric.is_integer() else str(numeric)
                except (TypeError, ValueError):
                    return None
                factor_text = (
                    await self._cover_conditions_text(factors)
                    if isinstance(factors, list) and factors
                    else None
                )
                if factor_text:
                    return (
                        f"{factor_text}; lors du contrôle périodique, "
                        f"l'automatisation a demandé la position {position_text} %"
                    )
                runtime_text = (
                    self._runtime_inputs_text(runtime_inputs)
                    if isinstance(runtime_inputs, dict) and runtime_inputs
                    else None
                )
                if runtime_text:
                    return (
                        f"lors du contrôle périodique, le calcul du volet a utilisé {runtime_text} "
                        f"et a demandé la position {position_text} %"
                    )
                return f"{trigger_text} et l'automatisation a demandé la position {position_text} %"

        if origin == "proven_factor_conjunction":
            factors = detail.get("factors")
            return await self._factors_text(factors) if isinstance(factors, list) else None

        if origin == "causal_sequence":
            factors = detail.get("factors")
            release = detail.get("release")
            factors_text = await self._factors_text(factors) if isinstance(factors, list) else None
            release_text = await self.render(release) if isinstance(release, dict) else None
            if factors_text and release_text:
                return f"{factors_text}; puis {release_text}"
            return factors_text or release_text

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
