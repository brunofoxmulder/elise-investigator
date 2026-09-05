from __future__ import annotations

from datetime import timedelta
from typing import Any

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev36 import _effect_context, _select_logbook_entry


class TargetedMemoryEnricher:
    """Persist the causality already exposed by HA 2026.9 Activity.

    No causal inference is performed here: for the functional event already
    selected by Investigator, copy Home Assistant's native Activity attribution
    into persistent conscious memory.
    """

    def __init__(self, ha, investigator=None):
        self.ha = ha
        self.investigator = investigator
        self.recorder = None
        self.logbook_reads = 0
        self.mcp_client = None

    def bind_recorder(self, recorder):
        self.recorder = recorder
        return self

    def set_mcp_client(self, client) -> None:
        self.mcp_client = client

    @staticmethod
    def _native_reason(entry: dict[str, Any]) -> str | None:
        value = entry.get("context_source") or entry.get("context_message")
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _native_origin(entry: dict[str, Any]) -> tuple[str, str | None, str | None]:
        if entry.get("context_user_id"):
            return "user", None, None
        source = str(entry.get("context_entity_id") or "").strip()
        source_name = str(entry.get("context_entity_id_name") or "").strip() or None
        if source.startswith("automation."):
            return "automation", source, source_name
        if source.startswith("script."):
            return "script", source, source_name
        return "unknown", None, None

    async def enrich(self, records: list[CausalRecord]) -> bool:
        if self.recorder is None:
            return False
        records = [record for record in records if record.record_id is not None]
        if not records:
            return False

        primaries = [record for record in records if record.attribute is None]
        anchor = max(primaries or records, key=lambda item: item.normalized_time())
        event_time = anchor.normalized_time()
        self.logbook_reads += 1
        entries = await self.ha.get_logbook(
            anchor.entity_id,
            event_time - timedelta(seconds=5),
            event_time + timedelta(seconds=5),
        )
        entry = _select_logbook_entry(entries, anchor)
        if not isinstance(entry, dict):
            return False

        origin_type, source_entity_id, source_name = self._native_origin(entry)
        reason = self._native_reason(entry)
        if origin_type == "unknown":
            return False

        proof = dict(anchor.trigger) if isinstance(anchor.trigger, dict) else {}
        proof["effect_context_id"] = _effect_context(anchor)
        proof["ha_activity"] = {
            key: entry.get(key)
            for key in (
                "when", "context_id", "context_event_type", "context_entity_id",
                "context_entity_id_name", "context_source", "context_message",
                "context_domain", "context_service", "context_user_id",
            )
            if entry.get(key) is not None
        }

        changed = False
        for original in records:
            current = self.recorder.get(original.record_id)
            if current is None:
                continue
            current.origin_type = origin_type
            current.source_entity_id = source_entity_id
            current.source_name = source_name
            current.reason = reason
            current.reason_code = "ha_2026_9_activity_native"
            current.trigger = proof
            current.confidence = "confirmed"
            self.recorder.update(current)
            changed = True
        return changed
