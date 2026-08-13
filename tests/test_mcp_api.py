"""dashboard/mcp_api.py — JSON-RPC transport and tool registry.

The MCP endpoint is served by the dashboard itself, so these tests cover the
protocol shape n8n and other clients rely on: initialize, tools/list, tools/call
and the notification that must produce no answer at all.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from dashboard import mcp_api


class ProtocolTest(unittest.TestCase):
    def call(self, method: str, params: dict | None = None, request_id=1):
        return mcp_api.handle({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})

    def test_initialize_echoes_the_clients_protocol_version(self) -> None:
        answer = self.call("initialize", {"protocolVersion": "2024-11-05"})
        self.assertEqual(answer["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(answer["result"]["serverInfo"]["name"], "acevo")

    def test_initialize_falls_back_to_our_version(self) -> None:
        answer = self.call("initialize", {})
        self.assertEqual(answer["result"]["protocolVersion"], mcp_api.PROTOCOL_VERSION)

    def test_initialized_notification_gets_no_answer(self) -> None:
        self.assertIsNone(mcp_api.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_ping(self) -> None:
        self.assertEqual(self.call("ping")["result"], {})

    def test_tools_are_listed_with_schemas(self) -> None:
        tools = self.call("tools/list")["result"]["tools"]
        names = {tool["name"] for tool in tools}
        for expected in (
            "status",
            "set_track",
            "set_mode",
            "select_cars",
            "balance_by_pi",
            "control",
            "leaderboard",
            "best_times",
            "session_history",
            "session_detail",
        ):
            self.assertIn(expected, names)
        for tool in tools:
            self.assertTrue(tool["description"], tool["name"])
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_unknown_method(self) -> None:
        self.assertEqual(self.call("does/not/exist")["error"]["code"], -32601)

    def test_unknown_tool(self) -> None:
        answer = self.call("tools/call", {"name": "nope", "arguments": {}})
        self.assertEqual(answer["error"]["code"], -32602)

    def test_bad_arguments_are_reported_as_invalid_params(self) -> None:
        answer = self.call("tools/call", {"name": "set_session", "arguments": {"wrong": 1}})
        self.assertEqual(answer["error"]["code"], -32602)


class ToolCallTest(unittest.TestCase):
    def call_tool(self, name: str, arguments: dict | None = None):
        return mcp_api.handle(
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}}
        )["result"]

    def test_result_carries_text_and_structured_content(self) -> None:
        with (
            patch.object(mcp_api.server_control, "status", return_value={"running": True}),
            patch.object(mcp_api.live, "snapshot", return_value={"drivers": [], "players": 0}),
        ):
            result = self.call_tool("status")
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["status"], {"running": True})
        self.assertIn("running", result["content"][0]["text"])

    def test_a_failing_tool_becomes_an_error_result_not_a_transport_error(self) -> None:
        """A broken tool must not take the JSON-RPC channel down with it."""
        with patch.object(mcp_api.server_control, "status", side_effect=RuntimeError("boom")):
            result = self.call_tool("status")
        self.assertTrue(result["isError"])
        self.assertIn("boom", result["content"][0]["text"])

    def test_control_rejects_an_unknown_action(self) -> None:
        result = self.call_tool("control", {"action": "explode"})
        self.assertIn("error", result["structuredContent"])
        self.assertIn("start", result["structuredContent"]["known"])

    def test_control_maps_to_the_server_action(self) -> None:
        with patch.object(mcp_api.server_control, "restart", return_value={"ok": True}) as restart:
            result = self.call_tool("control", {"action": "restart"})
        restart.assert_called_once()
        self.assertTrue(result["structuredContent"]["ok"])

    def test_set_track_reports_when_nothing_matches(self) -> None:
        with patch.object(mcp_api, "_form", return_value={"event": {"type": "GameModeType_PRACTICE", "track": ""}}):
            result = self.call_tool("set_track", {"track": "nürburgring-monaco"})
        self.assertIn("error", result["structuredContent"])

    def test_leaderboard_translates_internal_car_names(self) -> None:
        rows = [{"driver": "Max", "car": "ks_ferrari_296_gt3", "best_ms": 96369, "at": "", "steam_id": "", "laps": 2}]
        with (
            patch.object(mcp_api.history, "leaderboard", return_value=rows),
            patch.object(
                mcp_api.metadata,
                "build_metadata",
                return_value={
                    "cars": [{"internal_name": "ks_ferrari_296_gt3", "display_name": "Ferrari 296 GT3 - GT3"}]
                },
            ),
        ):
            result = self.call_tool("leaderboard", {"track": "Laguna"})
        self.assertEqual(result["structuredContent"]["leaderboard"][0]["car"], "Ferrari 296 GT3 - GT3")

    def test_balance_needs_at_least_two_cars(self) -> None:
        with patch.object(mcp_api, "_form", return_value={"cars": []}):
            result = self.call_tool("balance_by_pi")
        self.assertIn("error", result["structuredContent"])


if __name__ == "__main__":
    unittest.main()
