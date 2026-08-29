from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecorder
from memory_worker_dev44 import TargetedConsciousMemoryWorker as Dev44TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev45 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev44TargetedConsciousMemoryWorker):
    """Dev.45 keeps dev.44 capture and adds proven set-position fallback."""

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(
            enricher.ha, enricher.investigator
        ).bind_recorder(recorder)
