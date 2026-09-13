from __future__ import annotations

from typing import Any

from causal_renderer_v2 import CausalRendererV2
from causal_utils import number_text


class CausalRendererRC9(CausalRendererV2):
    async def render(self, cause: dict[str, Any] | None) -> str | None:
        if not isinstance(cause, dict):
            return None
        if str(cause.get("origin") or "") != "choose_default_failed_condition":
            return await super().render(cause)

        detail = cause.get("detail") if isinstance(cause.get("detail"), dict) else {}
        condition = detail.get("condition") if isinstance(detail.get("condition"), dict) else None
        if not isinstance(condition, dict):
            return None
        entity_id = str(condition.get("entity_id") or "")
        if not entity_id:
            return None

        label = entity_id
        unit = ""
        try:
            state = await self.ha.get_state(entity_id)
        except Exception:
            state = None
        if isinstance(state, dict):
            attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
            label = str(attrs.get("friendly_name") or entity_id)
            unit = str(attrs.get("unit_of_measurement") or "")

        relation = None
        threshold = None
        if condition.get("above") is not None:
            relation = ">"
            threshold = condition.get("above")
        elif condition.get("below") is not None:
            relation = "<"
            threshold = condition.get("below")
        if relation is None:
            return None

        threshold_text = number_text(threshold)
        suffix = f" {unit}" if unit else ""
        core = f"la condition « {label} {relation} {threshold_text}{suffix} » n'était pas satisfaite"
        delay = detail.get("prior_delay_text")
        if delay:
            return f"après le délai de {delay}, {core}"
        return core
