from __future__ import annotations

import json
import re
import unicodedata
from ipaddress import IPv4Address, IPv4Network, ip_address
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from mcp_client import MCPConnection, MCPProtocolSession, MCPReadOnlyClient, MCPReadOnlyError
from mcp_synthesis import synthesize_mcp_findings

_OPTIONS_FILE = Path("/data/options.json")
_PRIVATE_NETWORKS = (
    IPv4Network("10.0.0.0/8"),
    IPv4Network("172.16.0.0/12"),
    IPv4Network("192.168.0.0/16"),
)
_ALLOWED_TERRAIN_PORTS = frozenset({8123, 9584})
_MAX_PATH_LENGTH = 512
_PATH_SECRET_RE = re.compile(r"/(?:private_[^/?#\s]+|api/webhook/[^/?#\s]+)")
_TRACE_TOOL_NAME = "ha_get_automation_traces"


class InProcessMCPReadOnlyClient(MCPReadOnlyClient):
    """Connect to the HA-MCP server hosted by the HA-MCP Custom Component.

    The connect URL is supplied once through the Home Assistant App configuration
    and is stored only in /data/options.json. It is never returned by status/search
    endpoints.

    Dev.25 keeps the proven dev.24 synthesis unchanged and adds only a metadata
    probe for the live ``ha_get_automation_traces`` MCP contract. The probe reads
    the already-returned ``tools/list`` metadata and never calls the trace tool.
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
        return str(raw.get("mcp_connect_url") or "")

    @staticmethod
    def _normalize_copied_url(value: str) -> str:
        """Remove display/clipboard formatting chars without changing URL data."""
        text = str(value or "")
        return "".join(
            char
            for char in text
            if not char.isspace() and unicodedata.category(char) != "Cf"
        )

    @classmethod
    def _connection_from_url(cls, value: str) -> MCPConnection:
        raw = cls._normalize_copied_url(value)
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
        if port not in _ALLOWED_TERRAIN_PORTS:
            raise MCPReadOnlyError(
                "Port HA-MCP non autorisé pour ce prototype local (8123 ou 9584)"
            )

        path = parsed.path or ""
        if path in {"", "/"} or len(path) > _MAX_PATH_LENGTH:
            raise MCPReadOnlyError("Chemin de connexion HA-MCP absent ou invalide")
        if any(ord(char) < 33 or char.isspace() for char in path):
            raise MCPReadOnlyError("Chemin de connexion HA-MCP invalide")

        canonical_path = path.rstrip("/") or "/"
        return MCPConnection(
            slug="ha_mcp_tools_server",
            url=f"http://{address}:{port}{canonical_path}",
            host=str(address),
            port=port,
            read_only=True,
        )

    @classmethod
    def sanitize(cls, value):
        clean = super().sanitize(value)
        if isinstance(clean, str):
            return _PATH_SECRET_RE.sub("/[REDACTED_MCP_PATH]", clean)
        if isinstance(clean, list):
            return [cls.sanitize(item) for item in clean]
        if isinstance(clean, dict):
            return {str(key): cls.sanitize(item) for key, item in clean.items()}
        return clean

    @classmethod
    def _trace_contract_from_tools(cls, tools: dict[str, dict]) -> dict[str, object]:
        """Extract the trace-tool contract from tools/list without calling it."""
        if _TRACE_TOOL_NAME not in cls.ALLOWED_READ_TOOLS:
            raise MCPReadOnlyError("Outil traces absent de l'allow-list Investigator")

        tool = tools.get(_TRACE_TOOL_NAME)
        if not isinstance(tool, dict):
            raise MCPReadOnlyError("ha_get_automation_traces n'est pas exposé par HA-MCP")

        annotations = tool.get("annotations")
        if not isinstance(annotations, dict) or annotations.get("readOnlyHint") is not True:
            raise MCPReadOnlyError(
                "ha_get_automation_traces est refusé car non déclaré lecture seule"
            )

        schema = tool.get("inputSchema")
        if not isinstance(schema, dict):
            schema = {}

        return {
            "name": _TRACE_TOOL_NAME,
            "inputSchema": cls.sanitize(schema),
            "annotations": cls.sanitize(annotations),
            "contract_only": True,
            "tool_called": False,
        }

    async def discover(self) -> MCPConnection:
        return self._connection_from_url(self._load_connect_url())

    async def status(self) -> dict[str, object]:
        try:
            connection, protocol = await self.open_protocol()
            trace_contract = None
            trace_contract_error = None
            try:
                trace_contract = self._trace_contract_from_tools(protocol.tools)
            except MCPReadOnlyError as exc:
                trace_contract_error = self.sanitize(str(exc))

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
                "trace_tool_contract": trace_contract,
                "trace_tool_contract_error": trace_contract_error,
                "trace_probe_mode": "tools_list_metadata_only",
                "trace_tool_called": False,
            }
        except MCPReadOnlyError as exc:
            return {
                "available": False,
                "read_only": True,
                "provider": "ha_mcp_inprocess",
                "error": self.sanitize(str(exc)),
                "trace_probe_mode": "tools_list_metadata_only",
                "trace_tool_called": False,
            }

    async def open_protocol(self) -> tuple[MCPConnection, MCPProtocolSession]:
        # URL shape is not used as proof of identity. The actual MCP initialize
        # + tools/list exchange below is the validation step.
        connection = await self.discover()
        protocol = MCPProtocolSession(self, connection)
        await protocol.initialize()
        await protocol.list_tools()
        return connection, protocol

    async def research_entity(self, entity_id: str, question: str) -> dict[str, object]:
        """Run the proven dev.24 read-only recipe and deterministic synthesis."""
        result = await super().research_entity(entity_id, question)
        raw_findings = result.get("findings")
        findings = raw_findings if isinstance(raw_findings, list) else []
        synthesis = synthesize_mcp_findings(entity_id, question, findings)

        # Never let this layer become an alternative causal authority. It is a
        # presentation/synthesis layer over read-only facts only.
        result["mode"] = "deterministic_local_synthesis"
        result["answer"] = synthesis["answer"]
        result["local_synthesis"] = synthesis
        result["causal_verdict"] = None
        result["investigator_status_unchanged"] = True
        result["limits"] = [
            "Synthèse locale déterministe sans LLM.",
            "Faits observés et pistes de configuration sont séparés.",
            "Aucun verdict causal Investigator n'est créé, augmenté ni modifié.",
            "Dev.25 inspecte uniquement le contrat de l'outil traces via tools/list.",
            "ha_get_automation_traces n'est pas appelé par ce jalon.",
            "Seuls des outils MCP explicitement autorisés et déclarés readOnly sont appelés.",
        ]
        return result
