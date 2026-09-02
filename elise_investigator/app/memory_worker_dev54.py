from __future__ import annotations

from collections import deque
from typing import Any

from memory_worker_dev46 import TargetedConsciousMemoryWorker as Dev46TargetedConsciousMemoryWorker


_MAX_ASSIST_CONTEXTS = 256
_ASSIST_ACTIVE_STATES = frozenset({"processing", "responding"})


class TargetedConsciousMemoryWorker(Dev46TargetedConsciousMemoryWorker):
    """Dev.54 adds one proof path for Home Assistant Voice user commands.

    Dev.46 already recognizes direct Home Assistant user commands when HA supplies
    a ``user_id``. Home Assistant Voice can instead execute a command from an
    ``assist_satellite.*`` context without carrying a user id to the resulting
    service/state event.

    This worker keeps dev.46 unchanged and adds only a bounded context lineage:
    a voice-user lineage starts on an ``assist_satellite.*`` state transition to
    ``listening`` and can then extend through linked ``processing``/``responding``
    satellite contexts. A target change is promoted from ``unknown`` to the same
    generic ``user`` origin used by existing IHM/Alexa commands only when its own
    context or its matched service-command context is linked to that lineage.

    No temporal proximity is used as proof. Automation/script causes already
    established by dev.46 are never overwritten.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._assist_context_order: deque[str] = deque()
        self._assist_context_ids: set[str] = set()

    def _remember_assist_context(self, context_id: str | None) -> None:
        if not context_id or context_id in self._assist_context_ids:
            return
        self._assist_context_ids.add(context_id)
        self._assist_context_order.append(context_id)
        while len(self._assist_context_order) > _MAX_ASSIST_CONTEXTS:
            expired = self._assist_context_order.popleft()
            self._assist_context_ids.discard(expired)

    def _context_is_assist_user(self, context_id: str | None, parent_id: str | None) -> bool:
        return bool(
            (context_id and context_id in self._assist_context_ids)
            or (parent_id and parent_id in self._assist_context_ids)
        )

    def _capture_assist_satellite_context(self, event: dict[str, Any]) -> None:
        if str(event.get("event_type") or "") != "state_changed":
            return
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        entity_id = str(data.get("entity_id") or "")
        if not entity_id.startswith("assist_satellite."):
            return

        new_state = data.get("new_state") if isinstance(data.get("new_state"), dict) else {}
        state = str(new_state.get("state") or "")
        raw_context = new_state.get("context")
        if not isinstance(raw_context, dict):
            raw_context = event.get("context") if isinstance(event.get("context"), dict) else {}
        context_id = str(raw_context.get("id")) if raw_context.get("id") else None
        parent_id = str(raw_context.get("parent_id")) if raw_context.get("parent_id") else None

        # ``listening`` is the only root accepted as proof of an interactive
        # voice session. Later satellite phases may extend that exact lineage.
        if state == "listening":
            self._remember_assist_context(context_id)
        elif state in _ASSIST_ACTIVE_STATES and self._context_is_assist_user(context_id, parent_id):
            self._remember_assist_context(context_id)

    def _record_for_change(self, change):
        record = super()._record_for_change(change)
        if record.origin_type != "unknown":
            return record

        command = self._find_command(change)
        change_is_voice = self._context_is_assist_user(change.context_id, change.parent_id)
        command_is_voice = bool(
            command is not None
            and self._context_is_assist_user(command.context_id, command.parent_id)
        )
        if not (change_is_voice or command_is_voice):
            return record

        # Match the existing generic Home Assistant user contract exactly.
        record.origin_type = "user"
        record.reason_code = "home_assistant_user_context"
        record.confidence = "confirmed"
        self.linked_user += 1
        self.causes_missing = max(0, self.causes_missing - 1)
        return record

    async def _capture_event(self, event: dict[str, Any]) -> None:
        self._capture_assist_satellite_context(event)
        await super()._capture_event(event)

    async def stop(self) -> None:
        self._assist_context_order.clear()
        self._assist_context_ids.clear()
        await super().stop()
