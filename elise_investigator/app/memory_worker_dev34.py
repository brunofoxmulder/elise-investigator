from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from causal_events import ObservedChange, changes_from_state_event
from causal_recorder import CausalRecord, CausalRecorder
from ha_client import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

# Dev.34 deliberately remembers only controllable, user-visible objects. Sensor
# telemetry remains available in Home Assistant and can still be represented by
# an automation trigger, but it is not duplicated as a causal effect.
MEMORY_DOMAINS = frozenset(
    {
        "climate",
        "cover",
        "fan",
        "humidifier",
        "input_boolean",
        "light",
        "lock",
        "media_player",
        "switch",
        "vacuum",
        "water_heater",
    }
)

_PENDING_SECONDS = 300.0
_MAX_TRIGGERS = 512
_MAX_COMMANDS = 2048


@dataclass(slots=True)
class _AutomationTrigger:
    event_time: datetime
    context_id: str | None
    parent_id: str | None
    user_id: str | None
    entity_id: str | None
    name: str | None
    source: str | None


@dataclass(slots=True)
class _ServiceCommand:
    event_time: datetime
    context_id: str | None
    parent_id: str | None
    user_id: str | None
    domain: str
    service: str
    service_data: dict[str, Any]
    entity_ids: tuple[str, ...]


def _parse_time(value: Any) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _context(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("context")
    return raw if isinstance(raw, dict) else {}


def _string_or_none(value: Any) -> str | None:
    return str(value) if value is not None and str(value) else None


def _entity_ids(service_data: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []

    def add(raw: Any) -> None:
        if isinstance(raw, str):
            values.extend(part.strip() for part in raw.split(",") if part.strip())
        elif isinstance(raw, (list, tuple)):
            for item in raw:
                add(item)

    add(service_data.get("entity_id"))
    target = service_data.get("target")
    if isinstance(target, dict):
        add(target.get("entity_id"))
    return tuple(dict.fromkeys(values))


def _functional_reason(source: str | None) -> str | None:
    """Keep a proven trigger description unless it only says when we evaluated.

    A periodic/time trigger is useful technical evidence but is not, by itself,
    the functional reason for a runtime decision such as a shutter position.
    Dev.34 prefers no cause over a misleading cause.
    """

    if not source:
        return None
    text = source.strip()
    lower = text.casefold()
    if not text:
        return None
    if "time_pattern" in lower or lower.startswith("time pattern"):
        return None
    if lower.startswith("time at ") or lower in {"time", "timer"}:
        return None
    if lower.startswith("home assistant start") or lower.startswith("homeassistant start"):
        return None
    return text


def _compact_service_data(data: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "entity_id",
        "position",
        "tilt_position",
        "brightness",
        "brightness_pct",
        "percentage",
        "temperature",
        "target_temp_high",
        "target_temp_low",
        "hvac_mode",
        "preset_mode",
        "fan_mode",
        "source",
    }
    return {key: value for key, value in data.items() if key in keep}


class ConsciousMemoryWorker:
    """Build a small causal memory from HA events, without reverse searches.

    The normal path is deliberately cheap:
      automation_triggered -> call_service -> state_changed -> one local row.

    Automations that merely evaluate and do not change an object never create a
    memory row. There is no enrichment queue and no deep Home Assistant query in
    this worker.
    """

    def __init__(self, stream, recorder: CausalRecorder, enricher=None, **_kwargs: Any):
        self.stream = stream
        self.recorder = recorder
        # Kept only so the constructor remains compatible with dev.29 wiring.
        self.enricher = enricher
        self._stream_task: asyncio.Task | None = None
        self._stopping = False
        self._triggers: list[_AutomationTrigger] = []
        self._commands: list[_ServiceCommand] = []
        self.events_seen = 0
        self.state_events_seen = 0
        self.service_events_seen = 0
        self.automation_events_seen = 0
        self.records_written = 0
        self.linked_user = 0
        self.linked_automation = 0
        self.causes_missing = 0
        self.reconnects = 0
        self.last_error: str | None = None

    async def start(self) -> None:
        if self._stream_task is not None:
            return
        self._stopping = False
        self._stream_task = asyncio.create_task(
            self._stream_loop(), name="elise-conscious-memory"
        )

    async def stop(self) -> None:
        self._stopping = True
        if self._stream_task is not None:
            self._stream_task.cancel()
            await asyncio.gather(self._stream_task, return_exceptions=True)
        self._stream_task = None
        self._triggers.clear()
        self._commands.clear()

    def _prune_pending(self, now: datetime) -> None:
        cutoff = now.timestamp() - _PENDING_SECONDS
        self._triggers = [
            item for item in self._triggers if item.event_time.timestamp() >= cutoff
        ][-_MAX_TRIGGERS:]
        self._commands = [
            item for item in self._commands if item.event_time.timestamp() >= cutoff
        ][-_MAX_COMMANDS:]

    def _capture_automation(self, event: dict[str, Any]) -> None:
        self.automation_events_seen += 1
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        ctx = _context(event)
        self._triggers.append(
            _AutomationTrigger(
                event_time=_parse_time(event.get("time_fired")),
                context_id=_string_or_none(ctx.get("id")),
                parent_id=_string_or_none(ctx.get("parent_id")),
                user_id=_string_or_none(ctx.get("user_id")),
                entity_id=_string_or_none(data.get("entity_id")),
                name=_string_or_none(data.get("name")),
                source=_string_or_none(data.get("source")),
            )
        )

    def _capture_service(self, event: dict[str, Any]) -> None:
        self.service_events_seen += 1
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        service_data = data.get("service_data")
        if not isinstance(service_data, dict):
            service_data = {}
        ctx = _context(event)
        self._commands.append(
            _ServiceCommand(
                event_time=_parse_time(event.get("time_fired")),
                context_id=_string_or_none(ctx.get("id")),
                parent_id=_string_or_none(ctx.get("parent_id")),
                user_id=_string_or_none(ctx.get("user_id")),
                domain=str(data.get("domain") or ""),
                service=str(data.get("service") or ""),
                service_data=service_data,
                entity_ids=_entity_ids(service_data),
            )
        )

    @staticmethod
    def _context_score(
        left_id: str | None,
        left_parent: str | None,
        right_id: str | None,
        right_parent: str | None,
    ) -> int | None:
        if left_id and right_id and left_id == right_id:
            return 0
        if left_parent and right_id and left_parent == right_id:
            return 1
        if left_id and right_parent and left_id == right_parent:
            return 1
        if left_parent and right_parent and left_parent == right_parent:
            return 2
        return None

    def _find_command(self, change: ObservedChange) -> _ServiceCommand | None:
        changed_at = _parse_time(change.event_time)
        candidates: list[tuple[int, float, int, _ServiceCommand]] = []
        for command in self._commands:
            age = (changed_at - command.event_time).total_seconds()
            if age < -1.0 or age > _PENDING_SECONDS:
                continue
            context_score = self._context_score(
                change.context_id,
                change.parent_id,
                command.context_id,
                command.parent_id,
            )
            if context_score is None:
                continue
            target_penalty = 0 if change.entity_id in command.entity_ids else 1
            domain_penalty = 0 if command.domain == change.domain else 1
            candidates.append((context_score, target_penalty + domain_penalty, age, command))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return candidates[0][3]

    def _find_trigger(
        self, change: ObservedChange, command: _ServiceCommand | None
    ) -> _AutomationTrigger | None:
        changed_at = _parse_time(change.event_time)
        candidates: list[tuple[int, float, _AutomationTrigger]] = []
        for trigger in self._triggers:
            age = (changed_at - trigger.event_time).total_seconds()
            if age < -1.0 or age > _PENDING_SECONDS:
                continue
            scores: list[int] = []
            if command is not None:
                score = self._context_score(
                    command.context_id,
                    command.parent_id,
                    trigger.context_id,
                    trigger.parent_id,
                )
                if score is not None:
                    scores.append(score)
            score = self._context_score(
                change.context_id,
                change.parent_id,
                trigger.context_id,
                trigger.parent_id,
            )
            if score is not None:
                scores.append(score + 1)
            if scores:
                candidates.append((min(scores), age, trigger))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]

    def _record_for_change(self, change: ObservedChange) -> CausalRecord:
        command = self._find_command(change)
        trigger = self._find_trigger(change, command)
        origin_type = "unknown"
        source_entity_id = None
        source_name = None
        reason = None
        reason_code = None

        # A user id attached by Home Assistant is direct proof of a user-originated
        # command. Dev.34 does not guess whether that user command came from IHM or
        # voice; a later dev may refine the channel if HA exposes stronger proof.
        if change.user_id or (command is not None and command.user_id):
            origin_type = "user"
            reason_code = "home_assistant_user_context"
            self.linked_user += 1
        elif trigger is not None:
            origin_type = "automation"
            source_entity_id = trigger.entity_id
            source_name = trigger.name
            reason = _functional_reason(trigger.source)
            reason_code = (
                "automation_trigger_event" if reason else "automation_trigger_without_functional_reason"
            )
            self.linked_automation += 1

        proof: dict[str, Any] = {
            "effect_context_id": change.context_id,
            "effect_parent_id": change.parent_id,
        }
        if command is not None:
            proof["command"] = {
                "domain": command.domain,
                "service": command.service,
                "context_id": command.context_id,
                "parent_id": command.parent_id,
                "service_data": _compact_service_data(command.service_data),
            }
        if trigger is not None:
            proof["automation_trigger"] = {
                "entity_id": trigger.entity_id,
                "context_id": trigger.context_id,
                "parent_id": trigger.parent_id,
                "source": trigger.source,
            }

        if origin_type == "unknown" or (origin_type == "automation" and not reason):
            self.causes_missing += 1

        return CausalRecord(
            entity_id=change.entity_id,
            entity_name=change.entity_name,
            event_time=change.event_time,
            event_kind=change.event_kind,
            before_value=change.before_value,
            after_value=change.after_value,
            attribute=change.attribute,
            origin_type=origin_type,
            source_entity_id=source_entity_id,
            source_name=source_name,
            reason=reason,
            reason_code=reason_code,
            trigger=proof,
            confidence="confirmed",
        )

    def _capture_state(self, event: dict[str, Any]) -> None:
        self.state_events_seen += 1
        for change in changes_from_state_event(event):
            if change.domain not in MEMORY_DOMAINS:
                continue
            self.recorder.record(self._record_for_change(change))
            self.records_written += 1

    async def _capture_event(self, event: dict[str, Any]) -> None:
        self.events_seen += 1
        event_type = str(event.get("event_type") or "")
        if event_type == "automation_triggered":
            self._capture_automation(event)
        elif event_type == "call_service":
            self._capture_service(event)
        elif event_type == "state_changed":
            self._capture_state(event)
        if self.events_seen % 100 == 0:
            self._prune_pending(_parse_time(event.get("time_fired")))

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
                    raise HomeAssistantError("Flux mémoire terminé")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                self.reconnects += 1
                _LOGGER.warning("Conscious memory stream unavailable: %s; retry in %.0fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)

    def status(self) -> dict[str, Any]:
        return {
            "running": self._stream_task is not None and not self._stream_task.done(),
            "mode": "event_memory",
            "events_seen": self.events_seen,
            "state_events_seen": self.state_events_seen,
            "service_events_seen": self.service_events_seen,
            "automation_events_seen": self.automation_events_seen,
            "records_written": self.records_written,
            "linked_user": self.linked_user,
            "linked_automation": self.linked_automation,
            "causes_missing": self.causes_missing,
            "pending_commands": len(self._commands),
            "pending_automation_triggers": len(self._triggers),
            # Compatibility keys: dev.34 has no enrichment queue.
            "queue_depth": 0,
            "queue_capacity": 0,
            "records_enriched": 0,
            "enrichment_failures": 0,
            "enrichment_dropped": 0,
            "reconnects": self.reconnects,
            "last_error": self.last_error,
            "read_only_home_assistant": True,
        }
