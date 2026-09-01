from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecorder
from memory_worker_dev48 import TargetedConsciousMemoryWorker as Dev48TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev49 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev48TargetedConsciousMemoryWorker):
    """Dev.49 keeps dev.48 capture/retry and swaps only the corrected enrichment."""

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(
            enricher.ha, enricher.investigator
        ).bind_recorder(recorder)
