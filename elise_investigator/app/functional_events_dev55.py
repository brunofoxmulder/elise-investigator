from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TECHNICAL_STATES = frozenset({"unknown", "unavailable"})
# Domains whose primary state has a clear functional on/off meaning.  Covers keep
# their dedicated opening/closing episode logic and are deliberately not folded
# into this filter.
FUNCTIONAL_BINARY_DOMAINS = frozenset(
    {"light", "switch", "input_boolean", "fan", "humidifier"}
)


@dataclass(slots=True)
class FunctionalEventDecision:
    mode: str
    entity_id: str | None = None
    domain: str | None = None
    original_state: Any = None
    recovered_state: Any = None
    normalized_event: dict[str, Any] | None = None


class FunctionalStateTracker:
    """Separate functional changes from availability noise.

    Home Assistant legitimately records transitions through ``unavailable`` and
    ``unknown``.  For binary controllable objects those rows must not replace the
    last real off/on event merely because they are newer.

    The tracker is intentionally conservative:
    - functional -> technical: remember the last functional state, record nothing;
    - technical -> same functional state: availability recovery, record nothing;
    - technical -> different functional state: a real change happened while the
      object was unavailable, but its cause/time are not proven.  Emit a normalized
      functional transition that callers must keep ``indeterminate``;
    - recovery without an observed pre-outage state: record nothing (fail closed).
    """

    def __init__(self) -> None:
        self._before_outage: dict[str, Any] = {}

    @staticmethod
    def _parts(event: dict[str, Any]) -> tuple[str, str, Any, Any] | None:
        if not isinstance(event, dict) or event.get("event_type") != "state_changed":
            return None
        data = event.get("data")
        if not isinstance(data, dict):
            return None
        entity_id = str(data.get("entity_id") or "")
        if "." not in entity_id:
            return None
        domain = entity_id.split(".", 1)[0]
        old_state = data.get("old_state")
        new_state = data.get("new_state")
        if not isinstance(old_state, dict) or not isinstance(new_state, dict):
            return None
        return entity_id, domain, old_state.get("state"), new_state.get("state")

    @staticmethod
    def _rewrite_old_state(event: dict[str, Any], original_state: Any) -> dict[str, Any]:
        copied = dict(event)
        data = dict(event.get("data") or {})
        old_state = dict(data.get("old_state") or {})
        old_state["state"] = original_state
        data["old_state"] = old_state
        copied["data"] = data
        return copied

    def inspect(self, event: dict[str, Any]) -> FunctionalEventDecision:
        parts = self._parts(event)
        if parts is None:
            return FunctionalEventDecision(mode="pass")
        entity_id, domain, before, after = parts
        if domain not in FUNCTIONAL_BINARY_DOMAINS:
            return FunctionalEventDecision(
                mode="pass", entity_id=entity_id, domain=domain
            )

        before_technical = str(before).lower() in TECHNICAL_STATES
        after_technical = str(after).lower() in TECHNICAL_STATES

        if after_technical:
            if not before_technical:
                self._before_outage[entity_id] = before
            return FunctionalEventDecision(
                mode="technical_suppressed",
                entity_id=entity_id,
                domain=domain,
                original_state=self._before_outage.get(entity_id),
            )

        if before_technical:
            original = self._before_outage.pop(entity_id, None)
            if original is None:
                return FunctionalEventDecision(
                    mode="recovery_unanchored",
                    entity_id=entity_id,
                    domain=domain,
                    recovered_state=after,
                )
            if str(original) == str(after):
                return FunctionalEventDecision(
                    mode="recovery_same_state",
                    entity_id=entity_id,
                    domain=domain,
                    original_state=original,
                    recovered_state=after,
                )
            return FunctionalEventDecision(
                mode="recovery_changed_state",
                entity_id=entity_id,
                domain=domain,
                original_state=original,
                recovered_state=after,
                normalized_event=self._rewrite_old_state(event, original),
            )

        # A normal functional event closes any stale interruption marker.
        self._before_outage.pop(entity_id, None)
        return FunctionalEventDecision(
            mode="pass", entity_id=entity_id, domain=domain
        )

    def active_interruptions(self) -> int:
        return len(self._before_outage)

    def clear(self) -> None:
        self._before_outage.clear()
