from __future__ import annotations

from aiohttp import web

import main_mcp
from mcp_client_inprocess import InProcessMCPReadOnlyClient

# Terrain prototype 0.2.0-dev.27: preserve dev.26 bounded read-only trace
# exploration unchanged and add only a local clipboard text export in the UI.
# No new Home Assistant or MCP call is introduced by this checkpoint.
main_mcp.VERSION = "0.2.0-dev.27"
main_mcp.MCPReadOnlyClient = InProcessMCPReadOnlyClient


if __name__ == "__main__":
    web.run_app(main_mcp.create_app(), host="0.0.0.0", port=8099, access_log=None)
