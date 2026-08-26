from __future__ import annotations

import json
import re
from ipaddress import IPv4Address, IPv4Network, ip_address
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from mcp_client import MCPConnection, MCPProtocolSession, MCPReadOnlyClient, MCPReadOnlyError

_OPTIONS_FILE = Path("/data/options.json")
_PRIVATE_NETWORKS = (
    IPv4Network("10.0.0.0/8"),
    IPv4Network("172.16.0.0/12"),
    IPv4Network("192.168.0.0/16"),
)
_DIRECT_PATH_RE = re.compile(r"^/private_[A-Za-z0-9_-]{8,}/?$")
_WEBHOOK_PATH_RE = re.compile(r"^/api/webhook/mcp_[A-Za-z0-9_-]{8,}/?$")


class InProcessMCPReadOnlyClient(MCPReadOnlyClient):
    """Connect to the HA-MCP server hosted by the HA-MCP Custom Component.

    The connect URL is supplied once through the Home Assistant App configuration
    and is stored only in /data/options.json. It is never returned by status/search
    endpoints. Only local RFC1918 HTTP endpoints are accepted.

    This client deliberately does not use the Supervisor add-on inventory and does
    not need hassio_api/manager privileges. Read-only is enforced by the inherited
    fixed tool allow-list plus each MCP tool's readOnlyHint.
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        # MCPReadOnlyClient.__init__ requires SUPERVISOR_TOKEN because the old
        # add-on discovery path used Supervisor. The in-process path does not.
        self._session = session
        self._supervisor_token = ""

    @staticmethod
    def _load_connect_url() -> str:
        try:
            raw = json.loads(_OPTIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return ""
        if not isinstance(raw, dict):
            return ""
        return str(raw.get("mcp_connect_url") or "").strip()

    @classmethod
    def _connection_from_url(cls, value: str) -> MCPConnection:
        raw = str(value or "").strip()
        if not raw:
            raise MCPReadOnlyError(
                "URL locale HA-MCP non configurée dans les paramètres de l'App"
            )

        parsed = urlparse(raw)
        if parsed.scheme.lower() != "http":
            raise MCPReadOnlyError(
                "Élise Investigator accepte uniquement une URL HA-MCP locale en http"
            )
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise MCPReadOnlyError("URL locale HA-MCP invalide")

        host = parsed.hostname
        if not host:
            raise MCPReadOnlyError("Hôte HA-MCP absent")
        try:
            address = ip_address(host)
        except ValueError as exc:
            raise MCPReadOnlyError(
                "Utilise l'URL HA-MCP contenant l'adresse IPv4 locale de Home Assistant"
            ) from exc
        if not isinstance(address, IPv4Address) or not any(
            address in network for network in _PRIVATE_NETWORKS
        ):
            raise MCPReadOnlyError(
                "L'URL HA-MCP doit rester sur le réseau local privé"
            )

        try:
            port = parsed.port
        except ValueError as exc:
            raise MCPReadOnlyError("Port HA-MCP invalide") from exc
        if not port or port < 1 or port > 65535:
            raise MCPReadOnlyError("Port HA-MCP absent ou invalide")

        path = parsed.path or ""
        direct = bool(_DIRECT_PATH_RE.fullmatch(path))
        webhook = bool(_WEBHOOK_PATH_RE.fullmatch(path))
        if not direct and not webhook:
            raise MCPReadOnlyError(
                "URL HA-MCP non reconnue: utilise l'URL locale Direct access ou Local/LAN affichée par HA-MCP"
            )

        canonical_path = path.rstrip("/")
        return MCPConnection(
            slug="ha_mcp_tools_server",
            url=f"http://{address}:{port}{canonical_path}",
            host=str(address),
            port=port,
            read_only=True,
        )

    async def discover(self) -> MCPConnection:
        return self._connection_from_url(self._load_connect_url())

    async def status(self) -> dict[str, object]:
        try:
            connection, protocol = await self.open_protocol()
            return {
                "available": True,
                "read_only": True,
                "provider": "ha_mcp_inprocess",
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
                "provider": "ha_mcp_inprocess",
                "error": self.sanitize(str(exc)),
            }

    async def open_protocol(self) -> tuple[MCPConnection, MCPProtocolSession]:
        # Kept explicit here so the adapter contract is self-contained even if
        # the legacy Supervisor discovery changes later.
        connection = await self.discover()
        protocol = MCPProtocolSession(self, connection)
        await protocol.initialize()
        await protocol.list_tools()
        return connection, protocol
