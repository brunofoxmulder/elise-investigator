from __future__ import annotations

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev37 import _COVER_EPISODE_MAX_SECONDS
from targeted_memory_enricher_dev43 import TargetedMemoryEnricher as Dev43TargetedMemoryEnricher


class TargetedMemoryEnricher(Dev43TargetedMemoryEnricher):
    """Dev.44: retry enrichment of an unresolved cover start when terminal arrives.

    Terrain showed that the movement-start row can be stored before Home Assistant's
    Logbook/trace provenance is queryable. Dev.39 then rejects that row forever
    because its origin is still ``unknown`` when the terminal ``opening/closing``
    state arrives. Dev.44 reuses the already-recorded movement start, retries its
    normal targeted enrichment once at terminal time, then lets dev.43/dev.39 apply
    the existing proven episode propagation. No broad reverse search is added.
    """

    def _raw_cover_episode_start(self, anchor: CausalRecord) -> CausalRecord | None:
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
        return start

    async def enrich(self, records: list[CausalRecord]) -> bool:
        records = [record for record in records if record.record_id is not None]
        if not records:
            return False

        primaries = [record for record in records if record.attribute is None]
        anchor = max(primaries or records, key=lambda item: item.normalized_time())
        start = self._raw_cover_episode_start(anchor) if anchor.attribute is None else None

        # Retry only an unresolved automatic movement start. User-origin episodes
        # and starts already attributed to automation/script keep the existing path.
        if start is not None and start.origin_type == "unknown":
            await super().enrich([start])

        return await super().enrich(records)
