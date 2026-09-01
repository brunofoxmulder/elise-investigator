from __future__ import annotations

import asyncio

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev45 import (
    TargetedMemoryEnricher as Dev45TargetedMemoryEnricher,
)


_RETRY_DELAY_SECONDS = 2.0


class TargetedMemoryEnricher(Dev45TargetedMemoryEnricher):
    """Dev.48 retries one unresolved primary on/off cause after HA trace latency.

    The retry is deliberately narrow:
    - non-cover entity only;
    - primary state row only (attribute is None);
    - real off<->on transition only;
    - source already proven as automation/script;
    - source entity already known;
    - reason still missing after the normal dev.45 enrichment.

    No broader reverse search is introduced. Cover episode logic and brightness
    episode logic remain entirely delegated to the validated dev.45/dev.46 code.
    """

    @staticmethod
    def _is_retry_candidate(record: CausalRecord) -> bool:
        if record.entity_id.startswith("cover."):
            return False
        if record.attribute is not None:
            return False
        if record.event_kind not in {"turned_on", "turned_off"}:
            return False
        pair = (str(record.before_value).lower(), str(record.after_value).lower())
        if pair not in {("off", "on"), ("on", "off")}:
            return False
        if record.origin_type not in {"automation", "script"}:
            return False
        if not record.source_entity_id:
            return False
        return not bool(record.reason)

    async def enrich(self, records: list[CausalRecord]) -> bool:
        changed = await super().enrich(records)

        candidates: list[CausalRecord] = []
        for original in records:
            if original.record_id is None:
                continue
            current = self.recorder.get(original.record_id)
            if current is not None and self._is_retry_candidate(current):
                candidates.append(current)

        if not candidates:
            return changed

        # Home Assistant can expose the state effect before the source trace is
        # fully queryable. One bounded delayed retry of the same targeted source
        # is enough to close that race without changing the proof model.
        await asyncio.sleep(_RETRY_DELAY_SECONDS)
        retry_changed = await super().enrich(candidates)
        return changed or retry_changed
