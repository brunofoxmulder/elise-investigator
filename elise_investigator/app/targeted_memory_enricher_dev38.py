from __future__ import annotations

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev37 import (
    TargetedMemoryEnricher as Dev37TargetedMemoryEnricher,
    _COVER_EPISODE_MAX_SECONDS,
    _technical_reason,
)


class TargetedMemoryEnricher(Dev37TargetedMemoryEnricher):
    """Dev.38: preserve cover movement direction through terminal states.

    Home Assistant may terminate a partial closing with ``closing -> open`` while
    ``current_position`` still carries the actual partial position. Direction is
    therefore defined by the pre-terminal motion state, never inferred from the
    generic terminal state alone.
    """

    def _cover_episode_source(self, anchor: CausalRecord) -> CausalRecord | None:
        if not anchor.entity_id.startswith("cover.") or anchor.attribute is not None:
            return None

        motion = str(anchor.before_value or "").lower()
        terminal = str(anchor.after_value or "").lower()
        valid_terminals = {
            "closing": {"closed", "open"},
            "opening": {"open"},
        }
        if terminal not in valid_terminals.get(motion, set()):
            return None

        older = [
            item
            for item in self.recorder.for_entity(anchor.entity_id, limit=30)
            if item.record_id != anchor.record_id
            and item.attribute is None
            and item.normalized_time() < anchor.normalized_time()
        ]
        if not older:
            return None
        older.sort(key=lambda item: item.normalized_time(), reverse=True)
        start = older[0]
        if str(start.after_value or "").lower() != motion:
            return None
        age = (anchor.normalized_time() - start.normalized_time()).total_seconds()
        if age < 0 or age > _COVER_EPISODE_MAX_SECONDS:
            return None
        if start.origin_type == "user":
            return start
        if start.origin_type in {"automation", "script"} and start.reason and not _technical_reason(start.reason):
            return start
        return None
