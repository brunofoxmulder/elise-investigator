from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecorder
from memory_worker_dev49 import TargetedConsciousMemoryWorker as Dev49TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev50 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev49TargetedConsciousMemoryWorker):
    """Dev.50 keeps dev.49 capture/selection and swaps only causal enrichment."""

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(
            enricher.ha, enricher.investigator
        ).bind_recorder(recorder)
