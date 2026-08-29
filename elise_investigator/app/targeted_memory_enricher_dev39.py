from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecord
from targeted_memory_enricher_dev37 import _COVER_EPISODE_MAX_SECONDS, _technical_reason
from targeted_memory_enricher_dev38 import TargetedMemoryEnricher as Dev38TargetedMemoryEnricher


class TargetedMemoryEnricher(Dev38TargetedMemoryEnricher):
    """Dev.39: recover a proven cover cause from the movement start.

    Dev.38 correctly keeps the movement direction from the pre-terminal state, but
    it only accepts an automation/script start once a human ``reason`` is already
    materialized on that start record. Periodic automations deliberately capture
    no functional reason at first, even though their HA context and source are
    already proven. In that case, resolve exactly that source trace at the movement
    start, then propagate the recovered cause to the terminal state and the
    coalesced ``current_position`` row.

    No non-cover path is changed and no broad reverse search is introduced.
    """

    def _cover_episode_candidate(self, anchor: CausalRecord) -> CausalRecord | None:
        if not anchor.entity_id.startswith("cover.") or anchor.attribute is not None:
            return None

        motion = str(anchor.before_value or "").lower()
        terminal = str(anchor.after_value or "").lower()
        valid_terminals = {
            "closing": {"closed", "open"},
            "opening": {"open"},
        }
        if terminal not in valid_terminals.get(motion, set()):
            return None

        older = [
            item
            for item in self.recorder.for_entity(anchor.entity_id, limit=30)
            if item.record_id != anchor.record_id
            and item.attribute is None
            and item.normalized_time() < anchor.normalized_time()
        ]
        if not older:
            return None
        older.sort(key=lambda item: item.normalized_time(), reverse=True)
        start = older[0]
        if str(start.after_value or "").lower() != motion:
            return None
        age = (anchor.normalized_time() - start.normalized_time()).total_seconds()
        if age < 0 or age > _COVER_EPISODE_MAX_SECONDS:
            return None

        if start.origin_type == "user":
            return start
        if start.origin_type in {"automation", "script"} and start.source_entity_id:
            return start
        return None

    def _cover_episode_source(self, anchor: CausalRecord) -> CausalRecord | None:
        """Return only a source already safe to propagate without another read."""
        start = self._cover_episode_candidate(anchor)
        if start is None:
            return None
        if start.origin_type == "user":
            return start
        if start.reason and not _technical_reason(start.reason):
            return start
        return None

    async def _recover_cover_episode_reason(self, source: CausalRecord) -> CausalRecord | None:
        if source.origin_type not in {"automation", "script"} or not source.source_entity_id:
            return None
        if source.reason and not _technical_reason(source.reason):
            return source

        reason, trace_run_id, human_cause = await self._trace_reason(
            source,
            source.source_entity_id,
            source.source_name,
            source.origin_type,
        )
        if not reason or _technical_reason(reason):
            return None

        current = self.recorder.get(source.record_id) if source.record_id is not None else None
        if current is None:
            return None
        current.reason = reason
        current.reason_code = "cover_episode_source_trace"
        current.trace_run_id = trace_run_id or current.trace_run_id
        proof = dict(current.trigger) if isinstance(current.trigger, dict) else {}
        if human_cause:
            proof["human_cause"] = human_cause
        if self.last_trace_backend:
            proof["trace_backend"] = self.last_trace_backend
        current.trigger = proof
        current.confidence = "confirmed"
        self.recorder.update(current)
        return current

    async def enrich(self, records: list[CausalRecord]) -> bool:
        records = [record for record in records if record.record_id is not None]
        if not records:
            return False

        primaries = [record for record in records if record.attribute is None]
        anchor = max(primaries or records, key=lambda item: item.normalized_time())

        # Restrict the new behavior to a terminal primary state of a cover. State
        # and current_position emitted by that same HA event remain coalesced by
        # the existing dev.36 worker and receive one identical causal source.
        candidate = self._cover_episode_candidate(anchor) if anchor.attribute is None else None
        if candidate is not None:
            source = candidate
            if source.origin_type in {"automation", "script"} and (
                not source.reason or _technical_reason(source.reason)
            ):
                source = await self._recover_cover_episode_reason(source)
            if source is not None and (
                source.origin_type == "user"
                or (
                    source.origin_type in {"automation", "script"}
                    and source.reason
                    and not _technical_reason(source.reason)
                )
            ):
                return self._apply_cover_episode_source(records, source)

        # Preserve dev.38/dev.37 behavior verbatim for every other event and for
        # a cover episode whose start still cannot be proven causally.
        return await super().enrich(records)
