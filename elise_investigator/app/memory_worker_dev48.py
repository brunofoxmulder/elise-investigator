from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecorder
from memory_worker_dev46 import TargetedConsciousMemoryWorker as Dev46TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev48 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev46TargetedConsciousMemoryWorker):
    """Dev.48 keeps dev.46 capture/brightness episodes and swaps only enrichment."""

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(
            enricher.ha, enricher.investigator
        ).bind_recorder(recorder)
