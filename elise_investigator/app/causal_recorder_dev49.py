from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecord
from causal_recorder_dev47 import LatestPrimaryStateRecorder as Dev47LatestPrimaryStateRecorder


_TRANSIENT_STATES = {"unknown", "unavailable"}


def _is_stable_primary_transition(record: CausalRecord) -> bool:
    """Return True only for a real primary-state transition.

    Availability recovery is transport/integration lifecycle, not a user-visible
    on/off cause. Startup rows without a previous value are excluded for the same
    reason: they do not prove a transition.
    """

    if record.attribute is not None:
        return False
    before = None if record.before_value is None else str(record.before_value).strip().casefold()
    after = None if record.after_value is None else str(record.after_value).strip().casefold()
    if before is None or after is None or before == after:
        return False
    if before in _TRANSIENT_STATES or after in _TRANSIENT_STATES:
        return False
    return True


class LatestPrimaryStateRecorder(Dev47LatestPrimaryStateRecorder):
    """Dev.49 excludes availability loss/recovery from generic causal selection.

    The validated cover path is untouched. Explicit time/value/attribute clues also
    keep the historical selector. Only fully generic non-cover questions use this
    stricter primary-state choice.
    """

    def find_best(
        self,
        entity_id: str,
        *,
        observed_time: str | None = None,
        observed_value: Any = None,
        attribute: str | None = None,
        limit: int = 100,
    ) -> CausalRecord | None:
        if (
            entity_id.startswith("cover.")
            or observed_time is not None
            or observed_value is not None
            or attribute is not None
        ):
            return super().find_best(
                entity_id,
                observed_time=observed_time,
                observed_value=observed_value,
                attribute=attribute,
                limit=limit,
            )

        candidates = self.for_entity(entity_id, limit=limit)
        if not candidates:
            return None

        # Records are newest-first. Select the latest real state transition and
        # skip reconnect noise such as unavailable -> on/off.
        return next((item for item in candidates if _is_stable_primary_transition(item)), None)
