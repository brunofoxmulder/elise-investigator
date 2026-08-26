from __future__ import annotations

from aiohttp import web

import main_mcp
from mcp_client_inprocess import InProcessMCPReadOnlyClient

# Terrain prototype 0.2.0-dev.22: keep the existing Investigator + MCP console
# unchanged and validate the configured local HA-MCP endpoint by the real MCP
# handshake instead of guessing the integration's secret-path format.
main_mcp.VERSION = "0.2.0-dev.22"
main_mcp.MCPReadOnlyClient = InProcessMCPReadOnlyClient


if __name__ == "__main__":
    web.run_app(main_mcp.create_app(), host="0.0.0.0", port=8099, access_log=None)
