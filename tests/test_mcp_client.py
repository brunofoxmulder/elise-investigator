import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from mcp_client import MCPProtocolSession, MCPReadOnlyClient, MCPReadOnlyError


class _FakeClient(MCPReadOnlyClient):
    def __init__(self, *, read_only=True):
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            super().__init__(session=object())
        self.read_only = read_only
        self.rpc_calls = []

    async def _supervisor_get(self, path):
        if path == "/addons":
            return {
                "addons": [
                    {"slug": "abc123_ha_mcp_dev"},
                    {"slug": "abc123_ha_mcp"},
                ]
            }
        if path == "/addons/abc123_ha_mcp/info":
            return {
                "state": "started",
                "options": {
                    "read_only_mode": self.read_only,
                    "secret_path": "/private_1234567890abcdef",
                },
            }
        if path == "/addons/abc123_ha_mcp_dev/info":
            return {"state": "stopped", "options": {}}
        if path == "/network/info":
            return {
                "interfaces": [
                    {
                        "primary": True,
                        "enabled": True,
                        "connected": True,
                        "ipv4": {"ip_address": "192.168.1.50/24"},
                    }
                ]
            }
        raise AssertionError(path)

    async def _rpc(self, url, payload, *, session_id=None, expect_response=True):
        self.rpc_calls.append((url, payload, session_id, expect_response))
        method = payload.get("method")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {
                    "serverInfo": {"name": "ha-mcp", "version": "8.3.0"}
                },
            }, "session-1"
        if method == "notifications/initialized":
            return {}, session_id
        if method == "tools/list":
            tools = []
            for name in sorted(self.ALLOWED_READ_TOOLS):
                tools.append(
                    {
                        "name": name,
                        "annotations": {"readOnlyHint": True},
                        "inputSchema": {"type": "object"},
                    }
                )
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {"tools": tools},
            }, session_id
        if method == "tools/call":
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {
                    "structuredContent": {
                        "tool": payload["params"]["name"],
                        "ok": True,
                    }
                },
            }, session_id
        raise AssertionError(method)


class TestMCPReadOnlyClient(unittest.IsolatedAsyncioTestCase):
    def test_slug_priority_prefers_stable(self):
        slugs = MCPReadOnlyClient._matching_slugs(
            [
                {"slug": "repo_ha_mcp_dev"},
                {"slug": "repo_ha_mcp"},
                {"slug": "other"},
            ]
        )
        self.assertEqual(slugs, ["repo_ha_mcp", "repo_ha_mcp_dev"])

    async def test_discover_builds_local_secret_url_but_status_redacts_it(self):
        client = _FakeClient()
        connection = await client.discover()
        self.assertEqual(connection.host, "192.168.1.50")
        self.assertEqual(connection.port, 9583)
        self.assertIn("/private_1234567890abcdef", connection.url)

        status = await client.status()
        self.assertTrue(status["available"])
        self.assertTrue(status["read_only"])
        self.assertEqual(status["endpoint"], "http://192.168.1.50:9583/[SECRET]")
        self.assertNotIn("private_1234567890abcdef", str(status))

    async def test_discover_refuses_mcp_when_server_read_only_is_off(self):
        client = _FakeClient(read_only=False)
        with self.assertRaises(MCPReadOnlyError):
            await client.discover()

    def test_sanitize_redacts_secret_fields_and_private_paths(self):
        clean = MCPReadOnlyClient.sanitize(
            {
                "api_token": "abc",
                "message": "connect /private_abcdefghijklmnop with Bearer SECRET",
                "nested": [{"password": "pw"}],
            }
        )
        self.assertEqual(clean["api_token"], "[REDACTED]")
        self.assertNotIn("private_abcdefghijklmnop", clean["message"])
        self.assertIn("Bearer [REDACTED]", clean["message"])
        self.assertEqual(clean["nested"][0]["password"], "[REDACTED]")

    def test_parse_streamable_http_sse(self):
        parsed = MCPReadOnlyClient._parse_mcp_body(
            "text/event-stream",
            'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n',
        )
        self.assertEqual(parsed["result"]["ok"], True)

    async def test_protocol_refuses_tool_not_in_hard_allow_list(self):
        client = _FakeClient()
        connection = await client.discover()
        protocol = MCPProtocolSession(client, connection)
        await protocol.initialize()
        await protocol.list_tools()
        protocol.tools["ha_call_service"] = {
            "name": "ha_call_service",
            "annotations": {"readOnlyHint": False},
        }
        with self.assertRaises(MCPReadOnlyError):
            await protocol.call_tool("ha_call_service", {})

    async def test_research_recipe_uses_only_expected_read_tools(self):
        client = _FakeClient()
        result = await client.research_entity(
            "cover.volet_salon_2", "Pourquoi le volet est-il à 40 % ?"
        )
        self.assertTrue(result["success"])
        self.assertEqual(
            result["tools_used"], ["ha_get_state", "ha_get_history", "ha_search"]
        )
        tool_calls = [
            payload["params"]["name"]
            for _, payload, _, _ in client.rpc_calls
            if payload.get("method") == "tools/call"
        ]
        self.assertEqual(tool_calls, result["tools_used"])
        self.assertNotIn("ha_call_service", tool_calls)


if __name__ == "__main__":
    unittest.main()
