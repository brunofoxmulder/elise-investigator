from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from ipaddress import ip_interface
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class MCPReadOnlyError(RuntimeError):
    """Raised when the local MCP read-only contract cannot be satisfied."""


@dataclass(slots=True)
class MCPConnection:
    """Resolved local HA-MCP connection. The URL is secret and never serialized."""

    slug: str
    url: str
    host: str
    port: int
    read_only: bool


class MCPProtocolSession:
    """Small Streamable-HTTP MCP session using only aiohttp."""

    def __init__(self, client: "MCPReadOnlyClient", connection: MCPConnection) -> None:
        self._client = client
        self._connection = connection
        self._session_id: str | None = None
        self._next_id = 1
        self.server_info: dict[str, Any] = {}
        self.tools: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        payload, session_id = await self._client._rpc(
            self._connection.url,
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "elise-investigator",
                        "version": "0.2.0-dev.17",
                    },
                },
            },
        )
        self._next_id += 1
        if "result" not in payload:
            raise MCPReadOnlyError("HA-MCP n'a pas accepté l'initialisation MCP")
        result = payload.get("result") or {}
        if isinstance(result, dict):
            info = result.get("serverInfo")
            if isinstance(info, dict):
                self.server_info = info
        self._session_id = session_id
        if self._session_id:
            await self._client._rpc(
                self._connection.url,
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                session_id=self._session_id,
                expect_response=False,
            )

    async def list_tools(self) -> dict[str, dict[str, Any]]:
        payload, _ = await self._client._rpc(
            self._connection.url,
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "tools/list",
                "params": {},
            },
            session_id=self._session_id,
        )
        self._next_id += 1
        result = payload.get("result") or {}
        raw_tools = result.get("tools") if isinstance(result, dict) else None
        tools: dict[str, dict[str, Any]] = {}
        if isinstance(raw_tools, list):
            for item in raw_tools:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if name:
                    tools[name] = item
        self.tools = tools
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in self._client.ALLOWED_READ_TOOLS:
            raise MCPReadOnlyError(f"Outil MCP non autorisé par Élise Investigator: {name}")
        tool = self.tools.get(name)
        if not tool:
            raise MCPReadOnlyError(f"Outil MCP indisponible: {name}")
        annotations = tool.get("annotations")
        if not isinstance(annotations, dict) or annotations.get("readOnlyHint") is not True:
            raise MCPReadOnlyError(f"Outil MCP refusé car non déclaré lecture seule: {name}")

        payload, _ = await self._client._rpc(
            self._connection.url,
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            session_id=self._session_id,
        )
        self._next_id += 1
        if "error" in payload:
            err = payload.get("error") or {}
            message = err.get("message") if isinstance(err, dict) else str(err)
            raise MCPReadOnlyError(f"Erreur MCP pour {name}: {message or 'erreur inconnue'}")
        return self._client.sanitize(payload.get("result"))


class MCPReadOnlyClient:
    """Discover and query the local HA-MCP app with a hard read-only allow-list.

    This adapter deliberately exposes no generic Supervisor request and no generic
    MCP tool call. Discovery uses Supervisor GET endpoints only. MCP calls are
    restricted both by a local allow-list and by each tool's readOnlyHint.
    """

    MCP_PORT = 9583
    MCP_STABLE_SUFFIX = "_ha_mcp"
    MCP_DEV_SUFFIX = "_ha_mcp_dev"
    ALLOWED_READ_TOOLS = frozenset(
        {
            "ha_get_state",
            "ha_get_history",
            "ha_search",
            "ha_get_automation_traces",
        }
    )

    _SECRET_KEY_RE = re.compile(
        r"token|authorization|secret|password|api[_-]?key|access[_-]?token",
        re.IGNORECASE,
    )
    _PRIVATE_PATH_RE = re.compile(r"/private_[A-Za-z0-9_-]{8,}")

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not self._supervisor_token:
            raise MCPReadOnlyError("SUPERVISOR_TOKEN absent")

    async def _supervisor_get(self, path: str) -> dict[str, Any]:
        allowed = path == "/addons" or path == "/network/info" or (
            path.startswith("/addons/") and path.endswith("/info")
        )
        if not allowed:
            raise MCPReadOnlyError(f"Lecture Supervisor non autorisée: {path}")
        headers = {
            "Authorization": f"Bearer {self._supervisor_token}",
            "Content-Type": "application/json",
        }
        try:
            async with self._session.get(
                f"http://supervisor{path}", headers=headers, timeout=10
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    raise MCPReadOnlyError(
                        f"Supervisor GET {path}: HTTP {response.status}"
                    )
                try:
                    raw = json.loads(text) if text else {}
                except json.JSONDecodeError as exc:
                    raise MCPReadOnlyError(
                        f"Réponse Supervisor invalide pour {path}"
                    ) from exc
        except TimeoutError as exc:
            raise MCPReadOnlyError(f"Timeout Supervisor GET {path}") from exc
        except aiohttp.ClientError as exc:
            raise MCPReadOnlyError(f"Connexion Supervisor impossible pour {path}") from exc

        if not isinstance(raw, dict):
            return {}
        data = raw.get("data", raw)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _matching_slugs(addons: list[dict[str, Any]]) -> list[str]:
        stable: list[str] = []
        dev: list[str] = []
        for addon in addons:
            slug = str(addon.get("slug") or "")
            if slug == "ha_mcp" or (slug.endswith(MCPReadOnlyClient.MCP_STABLE_SUFFIX) and not slug.endswith(MCPReadOnlyClient.MCP_DEV_SUFFIX)):
                stable.append(slug)
            elif slug == "ha_mcp_dev" or slug.endswith(MCPReadOnlyClient.MCP_DEV_SUFFIX):
                dev.append(slug)
        return stable + dev

    async def _host_ipv4(self) -> str:
        network = await self._supervisor_get("/network/info")
        interfaces = network.get("interfaces")
        if not isinstance(interfaces, list):
            raise MCPReadOnlyError("Supervisor ne fournit pas les interfaces réseau")
        candidates = [
            item
            for item in interfaces
            if isinstance(item, dict)
            and item.get("enabled") is not False
            and item.get("connected") is not False
        ]
        candidates.sort(key=lambda item: 0 if item.get("primary") else 1)
        for item in candidates:
            ipv4 = item.get("ipv4")
            if not isinstance(ipv4, dict):
                continue
            address = str(ipv4.get("ip_address") or "").strip()
            if not address:
                continue
            try:
                return str(ip_interface(address).ip)
            except ValueError:
                continue
        raise MCPReadOnlyError("Adresse IPv4 locale Home Assistant introuvable")

    async def discover(self) -> MCPConnection:
        listing = await self._supervisor_get("/addons")
        addons = listing.get("addons")
        if not isinstance(addons, list):
            raise MCPReadOnlyError("Liste des Apps Supervisor indisponible")
        slugs = self._matching_slugs([x for x in addons if isinstance(x, dict)])
        if not slugs:
            raise MCPReadOnlyError("App HA-MCP introuvable")

        selected_slug: str | None = None
        selected_info: dict[str, Any] | None = None
        for slug in slugs:
            info = await self._supervisor_get(f"/addons/{slug}/info")
            if info.get("state") == "started":
                selected_slug = slug
                selected_info = info
                break
        if not selected_slug or not selected_info:
            raise MCPReadOnlyError("HA-MCP est installé mais n'est pas démarré")

        options = selected_info.get("options")
        if not isinstance(options, dict) or not options:
            raise MCPReadOnlyError(
                "Options HA-MCP masquées: le prototype a besoin d'un accès Supervisor manager en lecture"
            )
        if options.get("read_only_mode") is not True:
            raise MCPReadOnlyError(
                "HA-MCP n'est pas en mode lecture seule; Élise Investigator refuse la connexion"
            )
        secret_path = str(options.get("secret_path") or "").strip()
        if not secret_path.startswith("/private_"):
            raise MCPReadOnlyError("Chemin secret HA-MCP indisponible ou invalide")

        host = await self._host_ipv4()
        return MCPConnection(
            slug=selected_slug,
            url=f"http://{host}:{self.MCP_PORT}{secret_path}",
            host=host,
            port=self.MCP_PORT,
            read_only=True,
        )

    @classmethod
    def sanitize(cls, value: Any) -> Any:
        if isinstance(value, dict):
            clean: dict[str, Any] = {}
            for key, item in value.items():
                if cls._SECRET_KEY_RE.search(str(key)):
                    clean[str(key)] = "[REDACTED]"
                else:
                    clean[str(key)] = cls.sanitize(item)
            return clean
        if isinstance(value, list):
            return [cls.sanitize(item) for item in value]
        if isinstance(value, str):
            text = cls._PRIVATE_PATH_RE.sub("/[REDACTED_MCP_PATH]", value)
            text = re.sub(
                r"Bearer\s+[A-Za-z0-9._~+/=:-]+",
                "Bearer [REDACTED]",
                text,
                flags=re.IGNORECASE,
            )
            return text
        return value

    @staticmethod
    def _parse_mcp_body(content_type: str, text: str) -> dict[str, Any] | None:
        if not text.strip():
            return None
        if "text/event-stream" in content_type:
            parsed: dict[str, Any] | None = None
            for line in text.splitlines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    candidate = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict):
                    parsed = candidate
            return parsed
        try:
            candidate = json.loads(text)
        except json.JSONDecodeError:
            return None
        return candidate if isinstance(candidate, dict) else None

    async def _rpc(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        expect_response: bool = True,
    ) -> tuple[dict[str, Any], str | None]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        try:
            async with self._session.post(
                url, headers=headers, json=payload, timeout=25
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    raise MCPReadOnlyError(f"HA-MCP HTTP {response.status}")
                issued_session = response.headers.get("Mcp-Session-Id") or session_id
                if not expect_response:
                    return {}, issued_session
                parsed = self._parse_mcp_body(
                    response.headers.get("Content-Type", ""), text
                )
                if not parsed:
                    raise MCPReadOnlyError("Réponse MCP vide ou invalide")
                return parsed, issued_session
        except TimeoutError as exc:
            raise MCPReadOnlyError("Timeout de connexion à HA-MCP") from exc
        except aiohttp.ClientError as exc:
            raise MCPReadOnlyError("Connexion locale à HA-MCP impossible") from exc

    async def open_protocol(self) -> tuple[MCPConnection, MCPProtocolSession]:
        connection = await self.discover()
        protocol = MCPProtocolSession(self, connection)
        await protocol.initialize()
        await protocol.list_tools()
        return connection, protocol

    async def status(self) -> dict[str, Any]:
        try:
            connection, protocol = await self.open_protocol()
            return {
                "available": True,
                "read_only": True,
                "addon_slug": connection.slug,
                "endpoint": f"http://{connection.host}:{connection.port}/[SECRET]",
                "server_info": self.sanitize(protocol.server_info),
                "tool_count": len(protocol.tools),
                "allowed_tools_available": sorted(
                    self.ALLOWED_READ_TOOLS.intersection(protocol.tools)
                ),
            }
        except MCPReadOnlyError as exc:
            return {
                "available": False,
                "read_only": True,
                "error": self.sanitize(str(exc)),
            }

    async def research_entity(self, entity_id: str, question: str) -> dict[str, Any]:
        """Run the first deterministic MCP research recipe, without any LLM."""
        connection, protocol = await self.open_protocol()
        recipe = [
            (
                "ha_get_state",
                {"entity_id": entity_id},
            ),
            (
                "ha_get_history",
                {
                    "entity_ids": entity_id,
                    "source": "history",
                    "start_time": "3h",
                    "minimal_response": False,
                    "significant_changes_only": False,
                    "limit": 100,
                    "order": "desc",
                },
            ),
            (
                "ha_search",
                {
                    "query": entity_id,
                    "search_types": ["automation", "script"],
                },
            ),
        ]

        findings: list[dict[str, Any]] = []
        tools_used: list[str] = []
        for tool_name, arguments in recipe:
            if tool_name not in protocol.tools:
                findings.append(
                    {
                        "tool": tool_name,
                        "success": False,
                        "error": "outil non exposé par HA-MCP",
                    }
                )
                continue
            try:
                result = await protocol.call_tool(tool_name, arguments)
                findings.append(
                    {"tool": tool_name, "success": True, "result": result}
                )
                tools_used.append(tool_name)
            except MCPReadOnlyError as exc:
                findings.append(
                    {
                        "tool": tool_name,
                        "success": False,
                        "error": self.sanitize(str(exc)),
                    }
                )

        return {
            "engine": "ha-mcp-local",
            "mode": "deterministic_read_only_probe",
            "success": any(item.get("success") for item in findings),
            "read_only": True,
            "entity_id": entity_id,
            "question": question,
            "answer": (
                "Recherche MCP locale terminée. Ce prototype affiche les données brutes "
                "d'état, d'historique et de recherche de configuration; aucun LLM n'interprète encore ces résultats."
            ),
            "tools_used": tools_used,
            "findings": findings,
            "limits": [
                "Prototype local sans IA: pas encore de raisonnement adaptatif.",
                "Aucun verdict Investigator n'est modifié par cette recherche MCP.",
                "Seuls des outils MCP explicitement autorisés et déclarés readOnly sont appelés.",
            ],
            "mcp": {
                "addon_slug": connection.slug,
                "endpoint": f"http://{connection.host}:{connection.port}/[SECRET]",
                "server_info": self.sanitize(protocol.server_info),
                "tool_count": len(protocol.tools),
            },
        }
