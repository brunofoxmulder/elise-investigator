from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecorder
from memory_worker_dev37 import TargetedConsciousMemoryWorker as Dev37TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev38 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev37TargetedConsciousMemoryWorker):
    """Dev.38 keeps dev.37 capture/coalescing and fixes cover episode direction."""

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(
            enricher.ha, enricher.investigator
        ).bind_recorder(recorder)
