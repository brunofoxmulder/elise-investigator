import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "elise_investigator" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from mcp_client import MCPConnection
from mcp_client_inprocess import InProcessMCPReadOnlyClient
from mcp_trace_explorer import (
    DETAIL_SECTIONS,
    MAX_ACTIONS,
    MAX_CANDIDATES,
    TRACE_LIST_LIMIT,
    explore_bounded_traces,
)

TRACE_TOOL = "ha_get_automation_traces"


def _trace_tool(read_only=True):
    return {
        "name": TRACE_TOOL,
        "annotations": {
            "readOnlyHint": read_only,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    }


def _synthesis(candidate_count=2, event_time="2026-08-26T14:40:00+00:00"):
    return {
        "facts": [
            {
                "type": "recent_history",
                "events": [
                    {
                        "state": "closed",
                        "current_position": 0,
                        "time": event_time,
                    }
                ],
            }
        ],
        "configuration_leads": [
            {"entity_id": f"automation.test_{index}", "name": f"Test {index}"}
            for index in range(candidate_count)
        ],
    }


class TraceProtocol:
    def __init__(self, *, read_only=True):
        self.tools = {TRACE_TOOL: _trace_tool(read_only)}
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        automation_id = arguments["automation_id"]
        run_id = arguments.get("run_id")

        if run_id:
            actions = [
                {
                    "path": f"action/{index}",
                    "timestamp": f"2026-08-26T14:39:{index % 60:02d}+00:00",
                    "result": {"result": True, "index": index},
                    "variables": {"huge": "x" * 1000},
                }
                for index in range(25)
            ]
            return {
                "structuredContent": {
                    "success": True,
                    "automation_id": automation_id,
                    "run_id": run_id,
                    "timestamp": "2026-08-26T14:39:55+00:00",
                    "state": "stopped",
                    "trigger": {"platform": "time_pattern", "description": "test"},
                    "condition_results": [
                        {"path": "condition/0", "result": True}
                    ],
                    "action_trace": actions,
                }
            }

        if automation_id == "automation.test_0":
            timestamp = "2026-08-26T14:39:55+00:00"
        else:
            timestamp = "2026-08-26T13:00:00+00:00"
        return {
            "structuredContent": {
                "success": True,
                "automation_id": automation_id,
                "trace_count": 1,
                "total_available": 1,
                "has_more": False,
                "traces": [
                    {
                        "run_id": f"run-{automation_id}",
                        "timestamp": timestamp,
                        "state": "stopped",
                        "trigger": "test trigger",
                    }
                ],
            }
        }


class TestBoundedTraceExplorer(unittest.IsolatedAsyncioTestCase):
    async def test_selects_one_temporally_close_detail_and_compacts_it(self):
        protocol = TraceProtocol()
        result = await explore_bounded_traces(protocol, _synthesis(), lambda value: value)

        self.assertEqual(result["status"], "detail_selected")
        self.assertTrue(result["trace_tool_called"])
        self.assertEqual(result["candidates_queried"], 2)
        self.assertEqual(result["selected_run"]["automation_id"], "automation.test_0")
        self.assertEqual(result["selected_run"]["distance_seconds"], 5.0)
        self.assertFalse(result["selection_is_causal_proof"])
        self.assertIsNone(result["causal_verdict"])
        self.assertTrue(result["investigator_status_unchanged"])

        detail = result["selected_run_detail"]
        self.assertEqual(detail["action_count"], 25)
        self.assertEqual(len(detail["action_trace"]), MAX_ACTIONS)
        self.assertTrue(detail["actions_truncated"])
        self.assertTrue(all("variables" not in item for item in detail["action_trace"]))

        detail_call = protocol.calls[-1][1]
        self.assertEqual(detail_call["automation_id"], "automation.test_0")
        self.assertEqual(detail_call["run_id"], "run-automation.test_0")
        self.assertTrue(detail_call["deduplicate"])
        self.assertFalse(detail_call["detailed"])
        self.assertEqual(detail_call["sections"], DETAIL_SECTIONS)

    async def test_never_queries_more_than_candidate_limit(self):
        protocol = TraceProtocol()
        result = await explore_bounded_traces(
            protocol,
            _synthesis(candidate_count=MAX_CANDIDATES + 4),
            lambda value: value,
        )

        list_calls = [call for call in protocol.calls if "run_id" not in call[1]]
        self.assertEqual(len(list_calls), MAX_CANDIDATES)
        self.assertEqual(result["candidates_queried"], MAX_CANDIDATES)
        self.assertTrue(
            all(call[1]["limit"] == TRACE_LIST_LIMIT for call in list_calls)
        )

    async def test_no_history_anchor_means_no_trace_call(self):
        protocol = TraceProtocol()
        synthesis = _synthesis()
        synthesis["facts"] = []
        result = await explore_bounded_traces(protocol, synthesis, lambda value: value)

        self.assertEqual(result["status"], "not_run")
        self.assertFalse(result["trace_tool_called"])
        self.assertEqual(protocol.calls, [])

    async def test_non_read_only_trace_tool_is_never_called(self):
        protocol = TraceProtocol(read_only=False)
        result = await explore_bounded_traces(protocol, _synthesis(), lambda value: value)

        self.assertEqual(result["status"], "not_run")
        self.assertFalse(result["trace_tool_called"])
        self.assertEqual(protocol.calls, [])


class FullResearchProtocol(TraceProtocol):
    def __init__(self):
        super().__init__()
        self.server_info = {"name": "HA-MCP", "version": "8.3.0"}
        self.tools.update(
            {
                "ha_get_state": {"annotations": {"readOnlyHint": True}},
                "ha_get_history": {"annotations": {"readOnlyHint": True}},
                "ha_search": {"annotations": {"readOnlyHint": True}},
            }
        )

    async def call_tool(self, name, arguments):
        if name == "ha_get_state":
            self.calls.append((name, dict(arguments)))
            return {
                "structuredContent": {
                    "data": {
                        "entity_id": "cover.volet_test",
                        "state": "closed",
                        "attributes": {
                            "friendly_name": "Volet test",
                            "current_position": 0,
                        },
                    }
                }
            }
        if name == "ha_get_history":
            self.calls.append((name, dict(arguments)))
            return {
                "structuredContent": {
                    "data": {
                        "entities": [
                            {
                                "entity_id": "cover.volet_test",
                                "states": [
                                    {
                                        "state": "open",
                                        "last_changed": "2026-08-26T14:30:00+00:00",
                                        "attributes": {"current_position": 100},
                                    },
                                    {
                                        "state": "closed",
                                        "last_changed": "2026-08-26T14:40:00+00:00",
                                        "attributes": {"current_position": 0},
                                    },
                                ],
                            }
                        ]
                    }
                }
            }
        if name == "ha_search":
            self.calls.append((name, dict(arguments)))
            return {
                "structuredContent": {
                    "data": {
                        "results": [
                            {"entity_id": "automation.test_0", "name": "Test 0"},
                            {"entity_id": "automation.test_1", "name": "Test 1"},
                        ]
                    }
                }
            }
        return await super().call_tool(name, arguments)


class ResearchClient(InProcessMCPReadOnlyClient):
    def __init__(self, protocol):
        self._protocol = protocol
        self._session = None
        self._supervisor_token = ""

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


class TestDev26ResearchIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_research_keeps_investigator_verdict_untouched(self):
        protocol = FullResearchProtocol()
        client = ResearchClient(protocol)
        result = await client.research_entity(
            "cover.volet_test", "Pourquoi le volet test est fermé ?"
        )

        self.assertIsNone(result["causal_verdict"])
        self.assertTrue(result["investigator_status_unchanged"])
        self.assertEqual(result["trace_exploration"]["status"], "detail_selected")
        self.assertIn(TRACE_TOOL, result["tools_used"])
        self.assertFalse(
            result["local_synthesis"]["trace_exploration_summary"][
                "selection_is_causal_proof"
            ]
        )
        self.assertIn("n'est pas une preuve causale", result["answer"])


if __name__ == "__main__":
    unittest.main()
