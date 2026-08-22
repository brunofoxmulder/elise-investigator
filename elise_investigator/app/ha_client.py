from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp

_LOGGER = logging.getLogger(__name__)


class HomeAssistantError(RuntimeError):
    pass


class HAReadOnlyClient:
    """Narrow, intentionally read-only adapter to Home Assistant Core."""

    REST_BASE = "http://supervisor/core/api"
    WS_URL = "ws://supervisor/core/websocket"

    # Fail closed: no generic request method is exposed to the investigator.
    _ALLOWED_REST_GET_PREFIXES = (
        "/states",
        "/history/period",
        "/logbook",
        "/config/automation/config/",
        "/config/script/config/",
        "/config/scene/config/",
        "/config",
    )
    _ALLOWED_WS_TYPES = {
        "config/entity_registry/get",
        "config/entity_registry/list",
        "trace/list",
        "trace/get",
        "trace/contexts",
    }

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not self._token:
            raise HomeAssistantError("SUPERVISOR_TOKEN absent")
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not any(path == p or path.startswith(p) for p in self._ALLOWED_REST_GET_PREFIXES):
            raise HomeAssistantError(f"Lecture REST non autorisée: {path}")
        url = f"{self.REST_BASE}{path}"
        try:
            async with self._session.get(url, headers=self._headers, params=params, timeout=20) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise HomeAssistantError(f"HA GET {path}: HTTP {resp.status}: {text[:300]}")
                if not text:
                    return None
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        except asyncio.TimeoutError as exc:
            raise HomeAssistantError(f"Timeout HA GET {path}") from exc

    async def _ws(self, command: dict[str, Any]) -> Any:
        cmd_type = command.get("type")
        if cmd_type not in self._ALLOWED_WS_TYPES:
            raise HomeAssistantError(f"Commande WebSocket non autorisée: {cmd_type}")
        try:
            async with self._session.ws_connect(self.WS_URL, heartbeat=20, timeout=20) as ws:
                first = await ws.receive_json(timeout=10)
                if first.get("type") != "auth_required":
                    raise HomeAssistantError(f"Handshake WS inattendu: {first}")
                await ws.send_json({"type": "auth", "access_token": self._token})
                auth = await ws.receive_json(timeout=10)
                if auth.get("type") != "auth_ok":
                    raise HomeAssistantError(f"Authentification WS refusée: {auth}")
                payload = {"id": 1, **command}
                await ws.send_json(payload)
                while True:
                    msg = await ws.receive_json(timeout=20)
                    if msg.get("id") != 1:
                        continue
                    if msg.get("type") == "result":
                        if not msg.get("success"):
                            err = msg.get("error") or {}
                            raise HomeAssistantError(err.get("message") or str(err) or "Erreur WebSocket")
                        return msg.get("result")
        except asyncio.TimeoutError as exc:
            raise HomeAssistantError(f"Timeout WebSocket {cmd_type}") from exc

    async def get_config(self) -> dict[str, Any]:
        data = await self._get("/config")
        return data if isinstance(data, dict) else {}

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        return await self._get(f"/states/{quote(entity_id, safe='._')}")

    async def get_all_states(self) -> list[dict[str, Any]]:
        data = await self._get("/states")
        return data if isinstance(data, list) else []

    async def get_entity_registry(self, entity_id: str) -> dict[str, Any] | None:
        try:
            data = await self._ws({"type": "config/entity_registry/get", "entity_id": entity_id})
            return data if isinstance(data, dict) else None
        except HomeAssistantError as exc:
            if "not found" in str(exc).lower():
                return None
            raise

    async def list_entity_registry(self) -> list[dict[str, Any]]:
        data = await self._ws({"type": "config/entity_registry/list"})
        return data if isinstance(data, list) else []

    async def get_history(
        self,
        entity_id: str,
        start: datetime,
        end: datetime,
        *,
        significant_only: bool = False,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "filter_entity_id": entity_id,
            "end_time": end.isoformat(),
        }
        if significant_only:
            params["significant_changes_only"] = ""
        data = await self._get(f"/history/period/{quote(start.isoformat(), safe='')}", params=params)
        if isinstance(data, list) and data and isinstance(data[0], list):
            return data[0]
        return []

    async def get_logbook(self, entity_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        params = {"entity": entity_id, "end_time": end.isoformat()}
        data = await self._get(f"/logbook/{quote(start.isoformat(), safe='')}", params=params)
        return data if isinstance(data, list) else []

    async def get_automation_config(self, config_id: str) -> dict[str, Any] | None:
        try:
            data = await self._get(f"/config/automation/config/{quote(str(config_id), safe='')}")
            return data if isinstance(data, dict) else None
        except HomeAssistantError:
            return None

    async def get_script_config(self, script_id: str) -> dict[str, Any] | None:
        try:
            data = await self._get(f"/config/script/config/{quote(str(script_id), safe='')}")
            return data if isinstance(data, dict) else None
        except HomeAssistantError:
            return None

    async def get_scene_config(self, scene_id: str) -> dict[str, Any] | None:
        try:
            data = await self._get(f"/config/scene/config/{quote(str(scene_id), safe='')}")
            return data if isinstance(data, dict) else None
        except HomeAssistantError:
            return None

    async def list_traces(self, domain: str, item_id: str) -> list[dict[str, Any]]:
        if domain not in {"automation", "script"}:
            return []
        data = await self._ws({"type": "trace/list", "domain": domain, "item_id": str(item_id)})
        return data if isinstance(data, list) else []

    async def get_trace(self, domain: str, item_id: str, run_id: str) -> dict[str, Any] | None:
        if domain not in {"automation", "script"}:
            return None
        try:
            data = await self._ws(
                {"type": "trace/get", "domain": domain, "item_id": str(item_id), "run_id": str(run_id)}
            )
            return data if isinstance(data, dict) else None
        except HomeAssistantError as exc:
            if "could not be found" in str(exc).lower() or "not found" in str(exc).lower():
                return None
            raise

    async def get_trace_contexts(self, domain: str, item_id: str) -> Any:
        if domain not in {"automation", "script"}:
            return None
        try:
            return await self._ws({"type": "trace/contexts", "domain": domain, "item_id": str(item_id)})
        except HomeAssistantError:
            return None
