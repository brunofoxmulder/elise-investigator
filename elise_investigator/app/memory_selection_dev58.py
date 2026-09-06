from __future__ import annotations

from typing import Any

from causal_recorder import CausalRecord, CausalRecorder


_LIGHT_STATE_EVENTS = {"turned_on", "turned_off"}


def find_best_functional(
    recorder: CausalRecorder,
    entity_id: str,
    *,
    observed_time: str | None = None,
    observed_value: Any = None,
    attribute: str | None = None,
    limit: int = 100,
) -> CausalRecord | None:
    """Select the relevant functional event for a state question.

    dev.58 keeps the existing recorder semantics whenever the caller supplies an
    explicit time, value or attribute. For a plain light-state question, later
    brightness-only changes must not hide the last real OFF↔ON transition.
    """
    if (
        entity_id.startswith("light.")
        and observed_time is None
        and observed_value is None
        and attribute is None
    ):
        for item in recorder.for_entity(entity_id, limit=limit):
            if item.event_kind in _LIGHT_STATE_EVENTS:
                return item
        return None

    return recorder.find_best(
        entity_id,
        observed_time=observed_time,
        observed_value=observed_value,
        attribute=attribute,
        limit=limit,
    )
