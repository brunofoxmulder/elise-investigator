from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecorder
from memory_worker_dev36 import TargetedConsciousMemoryWorker as Dev36TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev37 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev36TargetedConsciousMemoryWorker):
    """Dev.37 keeps dev.36 capture/coalescing and changes enrichment only."""

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(
            enricher.ha, enricher.investigator
        ).bind_recorder(recorder)
