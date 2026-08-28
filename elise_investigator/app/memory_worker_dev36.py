from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from causal_events import changes_from_state_event
from causal_recorder import CausalRecord, CausalRecorder
from memory_worker_dev34 import ConsciousMemoryWorker, MEMORY_DOMAINS
from targeted_memory_enricher_dev36 import TargetedMemoryEnricher


_DEBOUNCE_SECONDS = 1.5
_MAX_PARALLEL_ENRICHMENTS = 2


@dataclass(slots=True)
class _Episode:
    generation: int = 0
    record_ids: list[int] = field(default_factory=list)
    task: asyncio.Task | None = None


class TargetedConsciousMemoryWorker(ConsciousMemoryWorker):
    """Dev.36 memory: durable effect first, one bounded causal read per episode.

    State + brightness from one light event and repeated cover position updates
    sharing the same HA context are coalesced. No enrichment item is dropped: the
    raw memory row is already durable, and pending targeted reads wait behind a
    tiny semaphore rather than entering a lossy FIFO queue.
    """

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        if enricher is None or not hasattr(enricher, "ha") or not hasattr(enricher, "investigator"):
            raise ValueError("Dev.36 requiert le client HA lecture seule existant")
        self.targeted = TargetedMemoryEnricher(enricher.ha, enricher.investigator).bind_recorder(recorder)
        self._episodes: dict[str, _Episode] = {}
        self._semaphore = asyncio.Semaphore(_MAX_PARALLEL_ENRICHMENTS)
        self.enrichment_runs = 0
        self.enrichment_success = 0
        self.enrichment_no_cause = 0
        self.enrichment_errors = 0
        self.episodes_coalesced = 0

    @staticmethod
    def _episode_key(change) -> str:
        context = change.context_id or change.parent_id
        if context:
            return f"{change.entity_id}|{context}"
        # No context means we cannot causally merge unrelated changes. The event
        # timestamp keeps the fallback key narrow while still coalescing state +
        # attributes emitted by the same state_changed event.
        return f"{change.entity_id}|{change.event_time}"

    def _schedule_episode(self, key: str, records: list[CausalRecord]) -> None:
        ids = [int(record.record_id) for record in records if record.record_id is not None]
        if not ids:
            return
        episode = self._episodes.setdefault(key, _Episode())
        if episode.record_ids:
            self.episodes_coalesced += len(ids)
        for record_id in ids:
            if record_id not in episode.record_ids:
                episode.record_ids.append(record_id)
        episode.generation += 1
        generation = episode.generation
        if episode.task is not None and not episode.task.done():
            episode.task.cancel()
        episode.task = asyncio.create_task(
            self._enrich_after_quiet(key, generation),
            name=f"elise-memory-enrich-{len(self._episodes)}",
        )

    async def _enrich_after_quiet(self, key: str, generation: int) -> None:
        try:
            await asyncio.sleep(_DEBOUNCE_SECONDS)
            episode = self._episodes.get(key)
            if episode is None or episode.generation != generation:
                return
            records = [
                record
                for record_id in episode.record_ids
                if (record := self.recorder.get(record_id)) is not None
            ]
            if not records:
                self._episodes.pop(key, None)
                return
            async with self._semaphore:
                self.enrichment_runs += 1
                try:
                    changed = await self.targeted.enrich(records)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.enrichment_errors += 1
                    return
                if changed and any(
                    (item := self.recorder.get(record.record_id or -1)) is not None
                    and (
                        item.origin_type == "user"
                        or (item.origin_type in {"automation", "script"} and bool(item.reason))
                    )
                    for record in records
                ):
                    self.enrichment_success += 1
                else:
                    self.enrichment_no_cause += 1
            current = self._episodes.get(key)
            if current is not None and current.generation == generation:
                self._episodes.pop(key, None)
        except asyncio.CancelledError:
            return

    def _capture_state(self, event: dict[str, Any]) -> None:
        self.state_events_seen += 1
        grouped: dict[str, list[CausalRecord]] = {}
        for change in changes_from_state_event(event):
            if change.domain not in MEMORY_DOMAINS:
                continue
            record = self.recorder.record(self._record_for_change(change))
            self.records_written += 1
            # Direct HA user context is already enough for the user-facing
            # "commande utilisateur" response; no Logbook/trace read is useful.
            if record.origin_type == "user":
                continue
            grouped.setdefault(self._episode_key(change), []).append(record)
        for key, records in grouped.items():
            self._schedule_episode(key, records)

    async def stop(self) -> None:
        tasks = [
            episode.task
            for episode in self._episodes.values()
            if episode.task is not None and not episode.task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._episodes.clear()
        await super().stop()

    def status(self) -> dict[str, Any]:
        data = super().status()
        active = sum(
            1
            for episode in self._episodes.values()
            if episode.task is not None and not episode.task.done()
        )
        data.update(
            {
                "mode": "targeted_memory_enrichment",
                "pending_episodes": active,
                "enrichment_runs": self.enrichment_runs,
                "enrichment_success": self.enrichment_success,
                "enrichment_no_cause": self.enrichment_no_cause,
                "enrichment_errors": self.enrichment_errors,
                "episodes_coalesced": self.episodes_coalesced,
                "logbook_reads": self.targeted.logbook_reads,
                "trace_reads": self.targeted.trace_reads,
                "max_parallel_enrichments": _MAX_PARALLEL_ENRICHMENTS,
                # Explicitly keep the old queue metrics at zero: dev.36 has no
                # bounded FIFO and therefore no queue-full/drop failure mode.
                "queue_depth": 0,
                "queue_capacity": 0,
                "enrichment_dropped": 0,
            }
        )
        return data
