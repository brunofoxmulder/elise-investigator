from __future__ import annotations

from typing import Any

from causal_events import changes_from_state_event
from causal_recorder import CausalRecord, CausalRecorder
from functional_events_dev55 import FunctionalStateTracker
from memory_worker_dev34 import MEMORY_DOMAINS
from memory_worker_dev54 import TargetedConsciousMemoryWorker as Dev54TargetedConsciousMemoryWorker


class TargetedConsciousMemoryWorker(Dev54TargetedConsciousMemoryWorker):
    """Dev.55 keeps dev.54 proof paths and filters technical availability noise.

    Normal causal capture remains native Home Assistant first: event Context,
    automation_triggered/call_service lineage, targeted Logbook enrichment and,
    only when useful, one targeted trace of the source already named by HA.

    The only new state-selection rule in this worker is functional continuity for
    binary controllable domains.  ``unavailable``/``unknown`` rows never become a
    newer functional event by themselves.  If the device comes back in a different
    functional state, the change is retained but deliberately marked indeterminate
    because HA did not prove when or why it changed during the outage.
    """

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self._functional_states = FunctionalStateTracker()
        self.technical_state_events_suppressed = 0
        self.availability_recoveries_suppressed = 0
        self.availability_recoveries_unanchored = 0
        self.availability_recoveries_changed = 0

    def _break_light_episode_if_needed(self, entity_id: str | None) -> None:
        if entity_id and entity_id.startswith("light."):
            # Dev.46 guarantees that a brightness cause is propagated only while
            # one proven transition episode remains continuous.  Availability
            # loss breaks that continuity and must therefore break the episode.
            self._break_brightness_transition(entity_id)

    def _record_indeterminate_recovery(self, event: dict[str, Any], *, original: Any) -> None:
        changes = changes_from_state_event(event)
        primary = next((item for item in changes if item.attribute is None), None)
        if primary is None or primary.domain not in MEMORY_DOMAINS:
            return
        record = CausalRecord(
            entity_id=primary.entity_id,
            entity_name=primary.entity_name,
            event_time=primary.event_time,
            event_kind=primary.event_kind,
            before_value=original,
            after_value=primary.after_value,
            attribute=None,
            origin_type="unknown",
            reason_code="availability_recovery_changed_functional_state",
            trigger={
                "availability_episode": {
                    "pre_outage_state": original,
                    "recovered_state": primary.after_value,
                    "cause_during_outage_proven": False,
                },
                "effect_context_id": primary.context_id,
                "effect_parent_id": primary.parent_id,
            },
            confidence="indeterminate",
        )
        self.recorder.record(record)
        self.records_written += 1
        self.causes_missing += 1

    def _capture_state(self, event: dict[str, Any]) -> None:
        decision = self._functional_states.inspect(event)
        if decision.mode == "pass":
            super()._capture_state(event)
            return

        # ``super`` is intentionally not called for technical/recovery rows, so
        # account for the state event here once.
        self.state_events_seen += 1
        self._break_light_episode_if_needed(decision.entity_id)

        if decision.mode == "technical_suppressed":
            self.technical_state_events_suppressed += 1
            return
        if decision.mode == "recovery_same_state":
            self.availability_recoveries_suppressed += 1
            return
        if decision.mode == "recovery_unanchored":
            self.availability_recoveries_unanchored += 1
            return
        if decision.mode == "recovery_changed_state" and decision.normalized_event is not None:
            self.availability_recoveries_changed += 1
            self._record_indeterminate_recovery(
                decision.normalized_event,
                original=decision.original_state,
            )

    async def stop(self) -> None:
        self._functional_states.clear()
        await super().stop()

    def status(self) -> dict[str, Any]:
        data = super().status()
        data.update(
            {
                "mode": "native_ha_first_functional_memory",
                "causal_strategy": "native_context_logbook_targeted_trace_then_persistent_memory",
                "legacy_reverse_search_normal_path": False,
                "technical_state_events_suppressed": self.technical_state_events_suppressed,
                "availability_recoveries_suppressed": self.availability_recoveries_suppressed,
                "availability_recoveries_unanchored": self.availability_recoveries_unanchored,
                "availability_recoveries_changed": self.availability_recoveries_changed,
                "active_availability_interruptions": self._functional_states.active_interruptions(),
            }
        )
        return data
