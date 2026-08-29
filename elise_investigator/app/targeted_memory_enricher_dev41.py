from __future__ import annotations

from causal_recorder import CausalRecord
from proven_factor_extractor import attach_first_proven_factor
from targeted_memory_enricher_dev39 import TargetedMemoryEnricher as Dev39TargetedMemoryEnricher


class TargetedMemoryEnricher(Dev39TargetedMemoryEnricher):
    """Dev.41: add one structured factor without changing dev.39 answers."""

    async def enrich(self, records: list[CausalRecord]) -> bool:
        changed = await super().enrich(records)
        factor_changed = False
        for original in records:
            if original.record_id is None:
                continue
            current = self.recorder.get(original.record_id)
            if current is None:
                continue
            if attach_first_proven_factor(current):
                self.recorder.update(current)
                factor_changed = True
        return changed or factor_changed
