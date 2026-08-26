from __future__ import annotations

from aiohttp import web

import main_mcp
from mcp_client_inprocess import InProcessMCPReadOnlyClient

# Terrain prototype 0.2.0-dev.28: preserve dev.26 bounded read-only trace
# exploration and dev.27 text export unchanged. The MCP console now owns an
# independent entity picker backed by the existing read-only entity catalog.
# Investigator does not need to run before an MCP request.
main_mcp.VERSION = "0.2.0-dev.28"
main_mcp.MCPReadOnlyClient = InProcessMCPReadOnlyClient


if __name__ == "__main__":
    web.run_app(main_mcp.create_app(), host="0.0.0.0", port=8099, access_log=None)
