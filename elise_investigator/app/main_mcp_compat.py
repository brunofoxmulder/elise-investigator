from __future__ import annotations

from aiohttp import web

import main_mcp
from mcp_client_compat import CompatibleMCPReadOnlyClient

# Terrain patch 0.2.0-dev.19: keep the multi-tool console unchanged and replace
# only HA-MCP discovery with the Supervisor-name-compatible matcher.
main_mcp.VERSION = "0.2.0-dev.19"
main_mcp.MCPReadOnlyClient = CompatibleMCPReadOnlyClient


if __name__ == "__main__":
    web.run_app(main_mcp.create_app(), host="0.0.0.0", port=8099, access_log=None)
