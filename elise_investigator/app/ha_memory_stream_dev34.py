from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from ha_client import HomeAssistantError


class HAMemoryEventStream:
    """Read-only Home Assistant event stream used by the dev.34 memory.

    Dev.34 listens only to events. The WebSocket connection can authenticate and
    subscribe, but this adapter deliberately exposes no generic command method and
    cannot call a Home Assistant service.
    """

    WS_URL = "ws://supervisor/core/websocket"
    EVENT_TYPES = {
        1: "state_changed",
        2: "call_service",
        3: "automation_triggered",
    }

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not self._token:
            raise HomeAssistantError("SUPERVISOR_TOKEN absent")

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        try:
            async with self._session.ws_connect(self.WS_URL, heartbeat=20, timeout=20) as ws:
                first = await ws.receive_json(timeout=10)
                if first.get("type") != "auth_required":
                    raise HomeAssistantError(f"Handshake WS inattendu: {first}")

                await ws.send_json({"type": "auth", "access_token": self._token})
                auth = await ws.receive_json(timeout=10)
                if auth.get("type") != "auth_ok":
                    raise HomeAssistantError("Authentification WS refusée")

                for subscription_id, event_type in self.EVENT_TYPES.items():
                    await ws.send_json(
                        {
                            "id": subscription_id,
                            "type": "subscribe_events",
                            "event_type": event_type,
                        }
                    )
                    ack = await ws.receive_json(timeout=10)
                    if (
                        ack.get("id") != subscription_id
                        or ack.get("type") != "result"
                        or ack.get("success") is not True
                    ):
                        error = ack.get("error") if isinstance(ack, dict) else None
                        raise HomeAssistantError(
                            f"Abonnement {event_type} refusé"
                            + (f": {error}" if error else "")
                        )

                async for message in ws:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        try:
                            payload = json.loads(message.data)
                        except (TypeError, json.JSONDecodeError):
                            continue
                    elif message.type == aiohttp.WSMsgType.BINARY:
                        try:
                            payload = json.loads(message.data.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                    elif message.type in {
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    }:
                        break
                    else:
                        continue

                    if not isinstance(payload, dict) or payload.get("type") != "event":
                        continue
                    subscription_id = payload.get("id")
                    expected = self.EVENT_TYPES.get(subscription_id)
                    event = payload.get("event")
                    if not expected or not isinstance(event, dict):
                        continue
                    if event.get("event_type") != expected:
                        continue
                    yield event
        except asyncio.CancelledError:
            raise
        except HomeAssistantError:
            raise
        except Exception as exc:
            raise HomeAssistantError(f"Flux mémoire interrompu: {exc}") from exc
