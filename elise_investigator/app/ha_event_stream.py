from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from ha_client import HomeAssistantError


class HAStateChangeStream:
    """Dedicated read-only Home Assistant `state_changed` subscription.

    This class intentionally exposes no generic WebSocket command method. The
    only post-authentication command it can send is `subscribe_events` scoped
    to `state_changed`. It therefore cannot be reused to mutate Home Assistant.
    """

    WS_URL = "ws://supervisor/core/websocket"
    SUBSCRIPTION_ID = 1

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not self._token:
            raise HomeAssistantError("SUPERVISOR_TOKEN absent")

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield Home Assistant `state_changed` events from one connection.

        Connection retry belongs to the recorder worker so restart/backoff
        policy stays outside this narrow transport adapter.
        """

        try:
            async with self._session.ws_connect(self.WS_URL, heartbeat=20, timeout=20) as ws:
                first = await ws.receive_json(timeout=10)
                if first.get("type") != "auth_required":
                    raise HomeAssistantError(f"Handshake WS inattendu: {first}")

                await ws.send_json({"type": "auth", "access_token": self._token})
                auth = await ws.receive_json(timeout=10)
                if auth.get("type") != "auth_ok":
                    raise HomeAssistantError(f"Authentification WS refusée: {auth}")

                await ws.send_json(
                    {
                        "id": self.SUBSCRIPTION_ID,
                        "type": "subscribe_events",
                        "event_type": "state_changed",
                    }
                )
                ack = await ws.receive_json(timeout=10)
                if (
                    ack.get("id") != self.SUBSCRIPTION_ID
                    or ack.get("type") != "result"
                    or ack.get("success") is not True
                ):
                    error = ack.get("error") if isinstance(ack, dict) else None
                    raise HomeAssistantError(
                        "Abonnement state_changed refusé"
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

                    if not isinstance(payload, dict):
                        continue
                    if payload.get("id") != self.SUBSCRIPTION_ID or payload.get("type") != "event":
                        continue
                    event = payload.get("event")
                    if not isinstance(event, dict) or event.get("event_type") != "state_changed":
                        continue
                    yield event
        except asyncio.CancelledError:
            raise
        except HomeAssistantError:
            raise
        except Exception as exc:
            raise HomeAssistantError(f"Flux state_changed interrompu: {exc}") from exc
