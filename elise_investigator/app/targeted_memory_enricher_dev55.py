from __future__ import annotations

import re
from typing import Any

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev45 import (
    TargetedMemoryEnricher as Dev45TargetedMemoryEnricher,
)


_NATIVE_TRIGGER_RE = re.compile(
    r"^(?P<kind>state|numeric state|device) of (?P<entity>[a-z0-9_]+\.[a-z0-9_]+)$",
    re.IGNORECASE,
)


def _native_logbook_reason(logbook: dict[str, Any] | None) -> str | None:
    """Return a conservative first-level cause already supplied by HA Logbook.

    Dev.54/dev.55 already preserve ``context_source`` as proof but historically do
    not promote it to ``reason``.  This helper deliberately does not infer a
    trigger value that Home Assistant did not expose.  It only turns the native
    runtime source into a readable causal statement.
    """
    if not isinstance(logbook, dict):
        return None

    raw = str(logbook.get("context_source") or "").strip()
    if not raw:
        return None

    lower = raw.casefold()
    if (
        "time_pattern" in lower
        or lower.startswith("time pattern")
        or lower.startswith("time at ")
        or lower in {"time", "timer"}
        or lower.startswith("home assistant start")
        or lower.startswith("homeassistant start")
    ):
        return None

    match = _NATIVE_TRIGGER_RE.match(raw)
    if match:
        entity_id = match.group("entity")
        shown = entity_id.split(".", 1)[1].replace("_", " ")
        return f"« {shown} » a déclenché l'automatisation"

    if lower.startswith("sun"):
        return "un événement solaire a déclenché l'automatisation"

    # Keep other explicit HA runtime sources as a conservative first-level cause.
    # Do not manufacture details (state value, threshold, branch, delay, etc.).
    return raw


class TargetedMemoryEnricher(Dev45TargetedMemoryEnricher):
    """Dev.55: promote HA's native Logbook source when trace detail is absent.

    Existing dev.45 behaviour remains untouched, including cover episodes and
    targeted trace semantics.  The only added rule is that an automation/script
    already confirmed by HA must not end as ``reason=None`` when the selected
    Logbook row itself contains a runtime ``context_source``.

    This is intentionally a conservative patch: trace may still provide a richer
    semantic explanation; native Logbook is used when that deepening yields none.
    """

    async def enrich(self, records: list[CausalRecord]) -> bool:
        changed = await super().enrich(records)

        for original in records:
            if original.record_id is None:
                continue
            current = self.recorder.get(original.record_id)
            if current is None:
                continue
            if current.origin_type not in {"automation", "script"} or current.reason:
                continue

            proof = current.trigger if isinstance(current.trigger, dict) else {}
            logbook = proof.get("logbook") if isinstance(proof.get("logbook"), dict) else None
            reason = _native_logbook_reason(logbook)
            if not reason:
                continue

            current.reason = reason
            marker = current.reason_code or "native_logbook_context"
            current.reason_code = f"{marker}+native_logbook_source"
            current.confidence = "confirmed"
            self.recorder.update(current)
            changed = True

        return changed
