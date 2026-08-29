from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecorder
from memory_worker_dev38 import TargetedConsciousMemoryWorker as Dev38TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev39 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev38TargetedConsciousMemoryWorker):
    """Dev.39 keeps dev.38 capture/coalescing and recovers cover start causes."""

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(
            enricher.ha, enricher.investigator
        ).bind_recorder(recorder)
