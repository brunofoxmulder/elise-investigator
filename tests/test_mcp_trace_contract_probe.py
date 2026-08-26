import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

APP_DIR = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from mcp_client import MCPConnection, MCPReadOnlyError
from mcp_client_inprocess import InProcessMCPReadOnlyClient


TRACE_TOOL = "ha_get_automation_traces"


def _trace_tool(*, read_only=True):
    return {
        "name": TRACE_TOOL,
        "description": "Must not be returned by the contract probe.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "automation_id": {"type": "string"},
                "run_id": {"type": ["string", "null"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["automation_id"],
        },
        "annotations": {
            "readOnlyHint": read_only,
            "idempotentHint": True,
            "openWorldHint": False,
            "title": "Get Automation Traces",
        },
    }


class FakeProtocol:
    def __init__(self):
        self.server_info = {"name": "HA-MCP", "version": "8.3.0"}
        self.tools = {
            "ha_get_state": {"annotations": {"readOnlyHint": True}},
            "ha_get_history": {"annotations": {"readOnlyHint": True}},
            "ha_search": {"annotations": {"readOnlyHint": True}},
            TRACE_TOOL: _trace_tool(),
        }
        self.called_tools = []

    async def call_tool(self, name, arguments):
        self.called_tools.append(name)
        if name == TRACE_TOOL:
            raise AssertionError("Dev.25 must never call ha_get_automation_traces")
        if name == "ha_get_state":
            return {
                "structuredContent": {
                    "data": {
                        "entity_id": "cover.volet_salon_2",
                        "state": "closed",
                        "attributes": {
                            "friendly_name": "volet salon",
                            "current_position": 0,
                        },
                    }
                }
            }
        if name == "ha_get_history":
            return {"structuredContent": {"data": {"entities": []}}}
        if name == "ha_search":
            return {"structuredContent": {"data": {"results": []}}}
        raise AssertionError(f"Unexpected tool: {name}")


class ProbeClient(InProcessMCPReadOnlyClient):
    def __init__(self, protocol):
        self._protocol = protocol

    async def open_protocol(self):
        return (
            MCPConnection(
                slug="ha_mcp_tools_server",
                url="http://192.168.1.20:9584/private_test",
                host="192.168.1.20",
                port=9584,
                read_only=True,
            ),
            self._protocol,
        )


class TestTraceContractMetadata(unittest.TestCase):
    def test_contract_returns_only_schema_annotations_and_guard_fields(self):
        contract = InProcessMCPReadOnlyClient._trace_contract_from_tools(
            {TRACE_TOOL: _trace_tool()}
        )
        self.assertEqual(contract["name"], TRACE_TOOL)
        self.assertEqual(contract["inputSchema"]["required"], ["automation_id"])
        self.assertTrue(contract["annotations"]["readOnlyHint"])
        self.assertTrue(contract["contract_only"])
        self.assertFalse(contract["tool_called"])
        self.assertNotIn("description", contract)

    def test_contract_rejects_tool_not_declared_read_only(self):
        with self.assertRaises(MCPReadOnlyError):
            InProcessMCPReadOnlyClient._trace_contract_from_tools(
                {TRACE_TOOL: _trace_tool(read_only=False)}
            )

    def test_contract_rejects_missing_trace_tool(self):
        with self.assertRaises(MCPReadOnlyError):
            InProcessMCPReadOnlyClient._trace_contract_from_tools({})


class TestTraceContractProbeRuntime(unittest.IsolatedAsyncioTestCase):
    async def test_status_reads_tools_list_metadata_without_calling_trace_tool(self):
        protocol = FakeProtocol()
        client = ProbeClient(protocol)
        status = await client.status()

        self.assertTrue(status["available"])
        self.assertTrue(status["read_only"])
        self.assertEqual(status["trace_probe_mode"], "tools_list_metadata_only")
        self.assertFalse(status["trace_tool_called"])
        self.assertTrue(status["trace_tool_contract"]["annotations"]["readOnlyHint"])
        self.assertEqual(protocol.called_tools, [])

    async def test_dev24_research_recipe_still_does_not_call_trace_tool(self):
        protocol = FakeProtocol()
        client = ProbeClient(protocol)
        result = await client.research_entity(
            "cover.volet_salon_2", "Pourquoi le volet salon est fermé ?"
        )

        self.assertEqual(
            protocol.called_tools,
            ["ha_get_state", "ha_get_history", "ha_search"],
        )
        self.assertNotIn(TRACE_TOOL, protocol.called_tools)
        self.assertIsNone(result["causal_verdict"])
        self.assertTrue(result["investigator_status_unchanged"])


if __name__ == "__main__":
    unittest.main()
