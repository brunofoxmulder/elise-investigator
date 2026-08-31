from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from causal_events import changes_from_state_event
from causal_recorder import CausalRecord, CausalRecorder
from memory_worker_dev34 import MEMORY_DOMAINS, _parse_time
from memory_worker_dev45 import TargetedConsciousMemoryWorker as Dev45TargetedConsciousMemoryWorker


_TRANSITION_TOLERANCE_SECONDS = 5.0
_MAX_TRANSITION_SECONDS = 24 * 60 * 60.0


@dataclass(slots=True)
class _BrightnessTransition:
    anchor_record_id: int
    started_at: Any
    expires_at: Any
    last_value: float | None
    direction: int


class TargetedConsciousMemoryWorker(Dev45TargetedConsciousMemoryWorker):
    """Dev.46 preserves the proven cause of one explicit light transition.

    Home Assistant can emit many ``brightness`` state changes while a single
    ``light.turn_on``/``light.turn_off`` command with ``transition`` is still in
    progress. Dev.45 records those changes independently, so a later brightness
    row can hide the proven cause captured at the beginning of the transition.

    Dev.46 keeps one bounded causal episode only when Home Assistant supplied an
    explicit light service command with a positive ``transition`` duration. Any
    later light command breaks the previous episode before its resulting state
    change is processed. A new command carrying its own transition can therefore
    start a new episode and become the new causal reference.

    Temporal proximity alone never creates an episode. Direction reversal,
    expiry, missing proof or ambiguous targeting all fail closed.
    """

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **kwargs: Any):
        super().__init__(stream, recorder, enricher=enricher, **kwargs)
        self._brightness_transitions: dict[str, _BrightnessTransition] = {}
        self.brightness_episode_inherited = 0
        self.brightness_episode_breaks = 0
        self.brightness_episode_rejected = 0

    @staticmethod
    def _transition_seconds(command) -> float | None:
        if command is None or command.domain != "light":
            return None
        raw = command.service_data.get("transition")
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            return None
        if seconds <= 0 or seconds > _MAX_TRANSITION_SECONDS:
            return None
        return seconds

    @staticmethod
    def _numeric(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _direction(cls, before: Any, after: Any) -> int:
        left = cls._numeric(before)
        right = cls._numeric(after)
        if left is None or right is None or left == right:
            return 0
        return 1 if right > left else -1

    @staticmethod
    def _anchor_is_proven(anchor: CausalRecord) -> bool:
        if anchor.origin_type == "user":
            return anchor.confidence == "confirmed"
        if anchor.origin_type in {"automation", "script"}:
            return (
                anchor.confidence in {"confirmed", "probable"}
                and bool(anchor.source_entity_id or anchor.reason)
            )
        return False

    @staticmethod
    def _copy_cause(anchor: CausalRecord, target: CausalRecord) -> None:
        target.origin_type = anchor.origin_type
        target.source_entity_id = anchor.source_entity_id
        target.source_name = anchor.source_name
        target.reason = anchor.reason
        marker = anchor.reason_code or anchor.origin_type
        target.reason_code = f"brightness_episode_inherited:{marker}"
        target.trigger = anchor.trigger
        target.factors = anchor.factors
        target.confidence = anchor.confidence
        target.trace_run_id = anchor.trace_run_id
        target.trace_path = anchor.trace_path

    def _break_brightness_transition(self, entity_id: str) -> None:
        if self._brightness_transitions.pop(entity_id, None) is not None:
            self.brightness_episode_breaks += 1

    def _capture_service(self, event: dict[str, Any]) -> None:
        super()._capture_service(event)
        if not self._commands:
            return
        command = self._commands[-1]
        if command.domain != "light":
            return

        # Every new light command supersedes a transition already in progress for
        # its explicit target. If HA only gives an area/device target and no entity
        # id, we cannot know which active light is affected, so fail closed and
        # invalidate every active brightness episode.
        if command.entity_ids:
            for entity_id in command.entity_ids:
                self._break_brightness_transition(entity_id)
        elif self._brightness_transitions:
            self.brightness_episode_breaks += len(self._brightness_transitions)
            self._brightness_transitions.clear()

    def _inherit_brightness_episode(
        self,
        change,
        record: CausalRecord,
        *,
        command,
    ) -> bool:
        # A state change linked to a new service command belongs to that command,
        # never to the previous brightness episode. The previous episode was
        # already broken in _capture_service.
        if command is not None:
            return False

        episode = self._brightness_transitions.get(change.entity_id)
        if episode is None:
            return False

        changed_at = _parse_time(change.event_time)
        if changed_at > episode.expires_at:
            self._break_brightness_transition(change.entity_id)
            self.brightness_episode_rejected += 1
            return False

        current = self._numeric(change.after_value)
        previous = episode.last_value
        if current is None or previous is None:
            self._break_brightness_transition(change.entity_id)
            self.brightness_episode_rejected += 1
            return False

        step_direction = 0 if current == previous else (1 if current > previous else -1)
        if episode.direction and step_direction and step_direction != episode.direction:
            self._break_brightness_transition(change.entity_id)
            self.brightness_episode_rejected += 1
            return False

        anchor = self.recorder.get(episode.anchor_record_id)
        if anchor is None or not self._anchor_is_proven(anchor):
            # The initial row can still be undergoing targeted enrichment. Do not
            # invent a cause meanwhile; a later brightness row may inherit once
            # the anchor has become proven.
            self.brightness_episode_rejected += 1
            episode.last_value = current
            if not episode.direction and step_direction:
                episode.direction = step_direction
            return False

        self._copy_cause(anchor, record)
        episode.last_value = current
        if not episode.direction and step_direction:
            episode.direction = step_direction
        self.brightness_episode_inherited += 1
        return True

    def _start_brightness_transition(self, change, record: CausalRecord, *, command) -> None:
        seconds = self._transition_seconds(command)
        if seconds is None or record.record_id is None:
            return
        if change.entity_id not in command.entity_ids:
            # Explicit entity targeting is required to prove which light owns the
            # transition. Area/device-only commands stay deliberately ungrouped.
            return

        started_at = command.event_time
        expires_at = started_at + timedelta(
            seconds=seconds + _TRANSITION_TOLERANCE_SECONDS
        )
        self._brightness_transitions[change.entity_id] = _BrightnessTransition(
            anchor_record_id=int(record.record_id),
            started_at=started_at,
            expires_at=expires_at,
            last_value=self._numeric(change.after_value),
            direction=self._direction(change.before_value, change.after_value),
        )

    def _capture_state(self, event: dict[str, Any]) -> None:
        self.state_events_seen += 1
        grouped: dict[str, list[CausalRecord]] = {}

        for change in changes_from_state_event(event):
            if change.domain not in MEMORY_DOMAINS:
                continue

            record = self._record_for_change(change)
            inherited = False
            command = None
            is_brightness = change.domain == "light" and change.attribute == "brightness"
            if is_brightness:
                command = self._find_command(change)
                if record.origin_type == "unknown":
                    inherited = self._inherit_brightness_episode(
                        change,
                        record,
                        command=command,
                    )

            record = self.recorder.record(record)
            self.records_written += 1

            if is_brightness:
                self._start_brightness_transition(change, record, command=command)

            # Direct user proof is final. Likewise, an inherited brightness cause
            # must not be overwritten by a new temporal/trace search around the
            # intermediate brightness row.
            if record.origin_type == "user" or inherited:
                continue

            grouped.setdefault(self._episode_key(change), []).append(record)

        for key, records in grouped.items():
            self._schedule_episode(key, records)

    async def stop(self) -> None:
        self._brightness_transitions.clear()
        await super().stop()

    def status(self) -> dict[str, Any]:
        data = super().status()
        data.update(
            {
                "active_brightness_episodes": len(self._brightness_transitions),
                "brightness_episode_inherited": self.brightness_episode_inherited,
                "brightness_episode_breaks": self.brightness_episode_breaks,
                "brightness_episode_rejected": self.brightness_episode_rejected,
            }
        )
        return data
