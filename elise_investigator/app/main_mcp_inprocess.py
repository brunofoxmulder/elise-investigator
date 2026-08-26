from __future__ import annotations

from aiohttp import web

import main_mcp
from mcp_client_inprocess import InProcessMCPReadOnlyClient

# Terrain prototype 0.2.0-dev.25: keep dev.24 behaviour unchanged and expose
# only the live tools/list contract of ha_get_automation_traces. The trace tool
# itself is not called by this checkpoint.
main_mcp.VERSION = "0.2.0-dev.25"
main_mcp.MCPReadOnlyClient = InProcessMCPReadOnlyClient


if __name__ == "__main__":
    web.run_app(main_mcp.create_app(), host="0.0.0.0", port=8099, access_log=None)
