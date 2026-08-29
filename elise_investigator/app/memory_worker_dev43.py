from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecorder
from memory_worker_dev39 import TargetedConsciousMemoryWorker as Dev39TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev43 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev39TargetedConsciousMemoryWorker):
    """Dev.43 keeps dev.39 capture/coalescing and adds structured causal factors."""

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(
            enricher.ha, enricher.investigator
        ).bind_recorder(recorder)
