from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecord
from causal_recorder_dev33 import RelevantCausalRecorder


class LatestPrimaryStateRecorder(RelevantCausalRecorder):
    """Dev.47 prefers the latest real primary-state change for generic questions.

    Home Assistant can emit useful control-attribute changes (for example a
    light ``brightness`` update) after the entity's last real state transition.
    For a generic causal question without an explicit time/value/attribute clue,
    those later attribute rows must not hide the last ``off <-> on`` event.

    Cover entities are deliberately excluded here. Their dev.45/dev.46 episode
    semantics are already field-validated and must remain byte-for-byte
    behaviourally unchanged by this selector.
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
        # Any explicit clue keeps the historical dev.33/dev.46 semantics.
        # Covers also keep that exact path, even for fully generic requests.
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

        # State rows are written only when old_state.state != new_state.state.
        # Therefore attribute=None is already the exact notion of a real primary
        # state transition, rather than an attribute-only bookkeeping update.
        primary = next((item for item in candidates if item.attribute is None), None)
        return primary or candidates[0]
