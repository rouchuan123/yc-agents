import unittest
import tempfile
from pathlib import Path

from yc_agents.harness.tool_gateway import ToolGateway
from yc_agents.tools.mcp_adapter import MCPToolAdapter
from yc_agents.tools.mcp_client import MCPClientConfig, StaticMCPClient
from yc_agents.tools.registry import ToolRegistry


class FakeMCPClient:
    def __init__(self):
        self.calls = []

    def call_tool(self, server_name, tool_name, arguments):
        self.calls.append(
            {
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
            }
        )
        return {
            "content": "mcp result",
        }


class FakeTrace:
    def __init__(self):
        self.events = []

    def record(self, event_type, payload=None):
        self.events.append(
            {
                "event_type": event_type,
                "payload": payload or {},
            }
        )


class TestMCPToolAdapter(unittest.TestCase):
    def test_static_mcp_client_returns_registered_tool_result(self):
        client = StaticMCPClient(
            {
                ("filesystem", "read_file"): {"content": "hello"},
            }
        )

        result = client.call_tool("filesystem", "read_file", {"path": "README.md"})

        self.assertEqual(result, {"content": "hello"})

    def test_mcp_client_config_loads_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp_servers.json"
            path.write_text(
                '{"servers":{"filesystem":{"type":"stdio","command":"npx","args":["x"]}}}',
                encoding="utf-8",
            )

            config = MCPClientConfig.from_file(path)

            self.assertEqual(config.servers["filesystem"]["command"], "npx")

    def test_adapter_calls_mcp_client(self):
        client = FakeMCPClient()
        adapter = MCPToolAdapter(
            name="mcp_search",
            description="Search through MCP.",
            server_name="research",
            tool_name="search",
            client=client,
        )

        result = adapter.run(query="agent runtime")

        self.assertEqual(result["type"], "mcp_tool_result")
        self.assertEqual(result["server_name"], "research")
        self.assertEqual(result["tool_name"], "search")
        self.assertEqual(result["result"], {"content": "mcp result"})
        self.assertEqual(client.calls[0]["arguments"], {"query": "agent runtime"})

    def test_adapter_can_be_called_through_tool_gateway(self):
        client = FakeMCPClient()
        registry = ToolRegistry()
        registry.register(
            MCPToolAdapter(
                name="mcp_search",
                description="Search through MCP.",
                server_name="research",
                tool_name="search",
                client=client,
            )
        )
        trace = FakeTrace()
        gateway = ToolGateway(
            tool_registry=registry,
            allowed_tools=["mcp_search"],
            trace=trace,
        )

        result = gateway.run_tool("mcp_search", query="runtime")

        self.assertEqual(result["result"]["content"], "mcp result")
        self.assertIn(
            "tool_called",
            [event["event_type"] for event in trace.events],
        )


if __name__ == "__main__":
    unittest.main()
