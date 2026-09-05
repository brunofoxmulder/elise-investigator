from __future__ import annotations

from typing import Any

from memory_worker_dev55 import TargetedConsciousMemoryWorker as Dev55Worker
from targeted_memory_enricher_dev57 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev55Worker):
    """Dev.57 keeps functional event selection and stores native HA Activity cause."""

    def __init__(self, stream, recorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(enricher.ha, enricher.investigator).bind_recorder(recorder)

    def status(self) -> dict[str, Any]:
        data = super().status()
        data.update({
            "mode": "ha_2026_9_activity_native",
            "causal_strategy": "read_store_return_native_activity",
            "default_query_window_hours": 12,
        })
        return data
