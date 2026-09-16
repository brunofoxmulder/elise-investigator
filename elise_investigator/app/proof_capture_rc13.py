"""Bounded capture on the existing HA event stream; no extra subscription/polling."""
from __future__ import annotations

import asyncio
import heapq
import itertools
from datetime import timedelta

from activity_reader_dev60 import _dt
from memory_worker_dev34 import MEMORY_DOMAINS


class ProofCapture:
    CAPACITY = 128
    RETRIES = (1.0, 3.0, 10.0, 30.0)
    READ_TIMEOUT = 10.0

    def __init__(self, reader, archive):
        self.reader, self.archive = reader, archive
        self._heap = []
        self._pending = set()
        self._counter = itertools.count()
        self._wake = asyncio.Event()
        self._task = None
        self.captured = self.missed = self.dropped = self.errors = self.native_only = 0

    def enqueue(self, event):
        if event.get("event_type") != "state_changed":
            return
        data = event.get("data") or {}
        entity = data.get("entity_id", "")
        old, new = data.get("old_state"), data.get("new_state")
        if (entity.partition(".")[0] not in MEMORY_DOMAINS
                or not isinstance(old, dict) or not isinstance(new, dict)):
            return
        before, after = old.get("state"), new.get("state")
        if before == after or before in {None, "unknown", "unavailable"} or after in {None, "unknown", "unavailable"}:
            return
        if entity.startswith("cover.") and after not in {"open", "closed"}:
            return  # Collect the terminal episode, not every motor/position update.
        stamp = _dt(new.get("last_changed") or event.get("time_fired"))
        if stamp is None:
            return
        key = (entity, stamp.isoformat(), after)
        if key in self._pending:
            return
        if len(self._pending) >= self.CAPACITY:
            self.dropped += 1
            return
        self._pending.add(key)
        self._schedule(key, 0)

    def _schedule(self, key, attempt):
        due = asyncio.get_running_loop().time() + self.RETRIES[attempt]
        heapq.heappush(self._heap, (due, next(self._counter), key, attempt))
        self._wake.set()

    async def capture_once(self, key):
        entity, stamp, after = key
        record = await self.reader._investigate_at(
            entity, end_time=_dt(stamp) + timedelta(microseconds=1),
            hours=self.archive.recorder.retention_hours, allow_upstream=False)
        if record is not None and record.normalized_time() == _dt(stamp) and record.origin_type in {"user", "alexa"}:
            return None  # Native attribution needs no expiring execution trace.
        if (record is None or record.normalized_time() != _dt(stamp)
                or record.after_value != after or not record.reason):
            return False
        # save is idempotent; restore only certifies this exact event's stored proof.
        if record.reason_code == "ha_logbook+retained_exact_trace":
            return True
        return self.archive.save(record)

    async def _run(self):
        while True:
            self._wake.clear()
            if not self._heap:
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=60)
                except asyncio.TimeoutError:
                    try:
                        self.archive.prune()
                    except Exception:
                        self.errors += 1
                continue
            due, _, key, attempt = self._heap[0]
            delay = due - asyncio.get_running_loop().time()
            if delay > 0:
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                continue
            heapq.heappop(self._heap)
            try:
                captured = await asyncio.wait_for(self.capture_once(key), self.READ_TIMEOUT)
            except Exception:
                self.errors += 1
                captured = False
            if captured is None:
                self.native_only += 1
                self._pending.discard(key)
            elif captured:
                self.captured += 1
                self._pending.discard(key)
            elif attempt + 1 < len(self.RETRIES):
                self._schedule(key, attempt + 1)
            else:
                self.missed += 1
                self._pending.discard(key)

    async def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="elise-proof-capture")

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self._heap.clear()
        self._pending.clear()

    def status(self):
        return {"running": self._task is not None and not self._task.done(),
                "pending": len(self._pending), "capacity": self.CAPACITY,
                "captured": self.captured, "missed": self.missed,
                "dropped": self.dropped, "errors": self.errors, "native_only": self.native_only}


class ObservedMemoryStream:
    def __init__(self, stream, capture):
        self.stream, self.capture = stream, capture

    def __getattr__(self, name):
        return getattr(self.stream, name)

    async def events(self):
        async for event in self.stream.events():
            try:
                self.capture.enqueue(event)
            except Exception:
                self.capture.errors += 1
            yield event  # Original memory worker receives every event unchanged.
