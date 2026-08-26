from __future__ import annotations

from aiohttp import web

import main_mcp
from mcp_client_inprocess import InProcessMCPReadOnlyClient

# Terrain prototype 0.2.0-dev.26: keep dev.24 synthesis and dev.25 live contract
# validation, then add bounded read-only trace exploration. The trace tool may be
# called only during an explicit MCP research request and never assigns causality.
main_mcp.VERSION = "0.2.0-dev.26"
main_mcp.MCPReadOnlyClient = InProcessMCPReadOnlyClient


if __name__ == "__main__":
    web.run_app(main_mcp.create_app(), host="0.0.0.0", port=8099, access_log=None)
