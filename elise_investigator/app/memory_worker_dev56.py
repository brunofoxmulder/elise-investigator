from __future__ import annotations

from typing import Any

from memory_worker_dev55 import TargetedConsciousMemoryWorker as Dev55TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev56 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev55TargetedConsciousMemoryWorker):
    """Dev.56 keeps dev.55 functional filtering and upgrades targeted enrichment."""

    def __init__(self, stream, recorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(
            enricher.ha, enricher.investigator
        ).bind_recorder(recorder)

    def status(self) -> dict[str, Any]:
        data = super().status()
        data.update(
            {
                "mode": "native_logbook_causality_first",
                "causal_strategy": "functional_event_native_logbook_targeted_trace_then_persistent_memory",
                "version_lineage": "dev55_functional_filter+dev56_native_logbook_reason",
            }
        )
        return data
