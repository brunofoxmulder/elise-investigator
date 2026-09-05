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
    """Use HA's runtime source as first-level cause without inventing detail."""
    if not isinstance(logbook, dict):
        return None

    raw = str(logbook.get("context_source") or logbook.get("context_message") or "").strip()
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
        label = entity_id.split(".", 1)[1].replace("_", " ")
        return f"« {label} » a déclenché l'automatisation"

    if lower.startswith("sun"):
        return "un événement solaire a déclenché l'automatisation"

    return raw


class TargetedMemoryEnricher(Dev45TargetedMemoryEnricher):
    """Dev.56: native Logbook first, targeted trace only for deeper semantics.

    All dev.45 cover/trace behaviour is preserved. After that targeted deepening,
    if HA has already confirmed an automation/script but no semantic reason was
    produced, the selected Logbook row may supply a conservative first-level
    causal reason through context_source/context_message.
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
