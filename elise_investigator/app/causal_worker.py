from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from causal_enricher import CausalEnricher, initial_record, needs_enrichment
from causal_events import ObservedChange, changes_from_state_event
from causal_recorder import CausalRecorder
from ha_client import HomeAssistantError
from ha_event_stream import HAStateChangeStream

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _PendingEnrichment:
    change: ObservedChange
    record_id: int


class CausalRecorderWorker:
    """Continuously capture HA changes, then enrich useful controls in background.

    The observed effect is committed to SQLite before any causal research. If a
    trace lookup fails, the journal keeps the event as indeterminate instead of
    losing it. Queue pressure can drop enrichment work but never the captured
    state change itself.
    """

    def __init__(
        self,
        stream: HAStateChangeStream,
        recorder: CausalRecorder,
        enricher: CausalEnricher,
        *,
        enrichment_workers: int = 2,
        queue_size: int = 200,
    ):
        self.stream = stream
        self.recorder = recorder
        self.enricher = enricher
        self.enrichment_workers = max(1, min(int(enrichment_workers), 4))
        self.queue: asyncio.Queue[_PendingEnrichment] = asyncio.Queue(maxsize=max(10, int(queue_size)))
        self._stream_task: asyncio.Task | None = None
        self._enrichment_tasks: list[asyncio.Task] = []
        self._stopping = False
        self.events_seen = 0
        self.records_written = 0
        self.records_enriched = 0
        self.enrichment_failures = 0
        self.enrichment_dropped = 0
        self.reconnects = 0
        self.last_error: str | None = None

    async def start(self) -> None:
        if self._stream_task is not None:
            return
        self._stopping = False
        self._stream_task = asyncio.create_task(self._stream_loop(), name="elise-causal-stream")
        self._enrichment_tasks = [
            asyncio.create_task(self._enrichment_loop(index), name=f"elise-causal-enrich-{index}")
            for index in range(self.enrichment_workers)
        ]

    async def stop(self) -> None:
        self._stopping = True
        tasks = [task for task in [self._stream_task, *self._enrichment_tasks] if task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._stream_task = None
        self._enrichment_tasks = []

    async def _capture_event(self, event: dict[str, Any]) -> None:
        self.events_seen += 1
        for change in changes_from_state_event(event):
            record = self.recorder.record(initial_record(change))
            self.records_written += 1
            if not needs_enrichment(change) or record.record_id is None:
                continue
            try:
                self.queue.put_nowait(_PendingEnrichment(change=change, record_id=record.record_id))
            except asyncio.QueueFull:
                self.enrichment_dropped += 1
                _LOGGER.warning(
                    "Causal enrichment queue full; event remains recorded indeterminate: %s",
                    change.entity_id,
                )

    async def _stream_loop(self) -> None:
        backoff = 1.0
        while not self._stopping:
            try:
                async for event in self.stream.events():
                    backoff = 1.0
                    self.last_error = None
                    await self._capture_event(event)
                    if self._stopping:
                        return
                if not self._stopping:
                    raise HomeAssistantError("Flux state_changed terminé")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                self.reconnects += 1
                _LOGGER.warning("Causal state stream unavailable: %s; retry in %.0fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)

    async def _enrichment_loop(self, worker_index: int) -> None:
        while True:
            try:
                pending = await self.queue.get()
                try:
                    record = self.recorder.get(pending.record_id)
                    if record is None:
                        continue
                    enriched = await self.enricher.enrich(pending.change, record)
                    self.recorder.update(enriched)
                    self.records_enriched += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.enrichment_failures += 1
                    self.last_error = str(exc)
                    _LOGGER.warning(
                        "Causal enrichment failed worker=%s entity=%s: %s",
                        worker_index,
                        pending.change.entity_id,
                        exc,
                    )
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                raise

    def status(self) -> dict[str, Any]:
        return {
            "running": self._stream_task is not None and not self._stream_task.done(),
            "queue_depth": self.queue.qsize(),
            "queue_capacity": self.queue.maxsize,
            "events_seen": self.events_seen,
            "records_written": self.records_written,
            "records_enriched": self.records_enriched,
            "enrichment_failures": self.enrichment_failures,
            "enrichment_dropped": self.enrichment_dropped,
            "reconnects": self.reconnects,
            "last_error": self.last_error,
            "read_only_home_assistant": True,
        }
