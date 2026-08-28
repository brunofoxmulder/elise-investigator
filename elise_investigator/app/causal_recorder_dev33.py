from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from causal_recorder import CausalRecord, CausalRecorder


class RelevantCausalRecorder(CausalRecorder):
    """Select the user-relevant effect when one HA event produced several rows.

    ``changes_from_state_event`` can legitimately emit both a primary state change
    and one or more control-attribute changes with the exact same ``event_time``.
    Those rows are useful and remain stored independently, but a generic causal
    question about the entity must not accidentally prefer the attribute row only
    because it received the highest SQLite id.

    Explicit clues always win: an attribute request stays on that attribute and an
    observed value is never ignored. Only an otherwise generic lookup applies the
    state-first preference inside the nearest/latest timestamp group.
    """

    @staticmethod
    def _prefer_primary_state(candidates: list[CausalRecord]) -> CausalRecord:
        primary = next((item for item in candidates if item.attribute is None), None)
        return primary or candidates[0]

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            wanted = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if wanted.tzinfo is None:
            wanted = wanted.replace(tzinfo=timezone.utc)
        return wanted.astimezone(timezone.utc)

    def find_best(
        self,
        entity_id: str,
        *,
        observed_time: str | None = None,
        observed_value: Any = None,
        attribute: str | None = None,
        limit: int = 100,
    ) -> CausalRecord | None:
        candidates = self.for_entity(entity_id, limit=limit)
        if attribute is not None:
            candidates = [item for item in candidates if item.attribute == attribute]
        if observed_value is not None:
            candidates = [
                item for item in candidates if self._same_value(item.after_value, observed_value)
            ]
        if not candidates:
            return None

        generic_lookup = attribute is None and observed_value is None
        wanted = self._parse_time(observed_time)

        if wanted is not None:
            distances = [
                abs((item.normalized_time() - wanted).total_seconds()) for item in candidates
            ]
            nearest_distance = min(distances)
            nearest = [
                item
                for item, distance in zip(candidates, distances)
                if abs(distance - nearest_distance) < 1e-9
            ]
            if generic_lookup:
                return self._prefer_primary_state(nearest)
            return nearest[0]

        if generic_lookup:
            latest_time = candidates[0].normalized_time()
            same_event = [
                item for item in candidates if item.normalized_time() == latest_time
            ]
            return self._prefer_primary_state(same_event)

        # Preserve the historical semantics when the caller supplied an explicit
        # value or attribute clue: rows are already ordered newest first.
        return candidates[0]
