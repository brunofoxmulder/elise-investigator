from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecorder
from memory_worker_dev43 import TargetedConsciousMemoryWorker as Dev43TargetedConsciousMemoryWorker
from targeted_memory_enricher_dev44 import TargetedMemoryEnricher


class TargetedConsciousMemoryWorker(Dev43TargetedConsciousMemoryWorker):
    """Dev.44 keeps dev.43 capture and retries unresolved cover starts at terminal."""

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self.targeted = TargetedMemoryEnricher(
            enricher.ha, enricher.investigator
        ).bind_recorder(recorder)
