import unittest

from yc_agents.harness.tool_gateway import ToolGateway, ToolNotAllowedError
from yc_agents.tools.base import BaseTool
from yc_agents.tools.registry import ToolRegistry


class FakeTool(BaseTool):
    name = "fake_tool"
    description = "A fake tool for tests."

    def run(self, text):
        return {
            "echo": text,
        }


class FakeFailingTool(BaseTool):
    name = "failing_tool"
    description = "A fake failing tool for tests."

    def run(self):
        raise RuntimeError("tool failed")


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


class FakeApprovalGate:
    def check_tool_call(self, tool_name, arguments):
        if tool_name == "fake_tool" and arguments.get("text") == "danger":
            return {
                "allowed": False,
                "needs_approval": True,
                "action": "tool_call",
                "reason": "dangerous test call",
                "tool_name": tool_name,
            }

        return {
            "allowed": True,
            "needs_approval": False,
            "action": "tool_call",
            "reason": "safe test call",
            "tool_name": tool_name,
        }


class TestToolGateway(unittest.TestCase):
    def test_allowed_tool_can_be_called(self):
        registry = ToolRegistry()
        registry.register(FakeTool())

        gateway = ToolGateway(
            tool_registry=registry,
            allowed_tools=["fake_tool"],
        )

        result = gateway.run_tool("fake_tool", "hello")

        self.assertEqual(result, {"echo": "hello"})

    def test_denies_tool_not_in_allowed_tools(self):
        registry = ToolRegistry()
        registry.register(FakeTool())

        gateway = ToolGateway(
            tool_registry=registry,
            allowed_tools=[],
        )

        with self.assertRaises(ToolNotAllowedError):
            gateway.run_tool("fake_tool", "hello")

    def test_records_tool_called(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        trace = FakeTrace()

        gateway = ToolGateway(
            tool_registry=registry,
            allowed_tools=["fake_tool"],
            trace=trace,
        )

        gateway.run_tool("fake_tool", "hello")

        event_types = [
            event["event_type"]
            for event in trace.events
        ]

        self.assertIn("tool_called", event_types)

    def test_records_tool_denied(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        trace = FakeTrace()

        gateway = ToolGateway(
            tool_registry=registry,
            allowed_tools=[],
            trace=trace,
        )

        with self.assertRaises(ToolNotAllowedError):
            gateway.run_tool("fake_tool", "hello")

        event_types = [
            event["event_type"]
            for event in trace.events
        ]

        self.assertIn("tool_denied", event_types)

    def test_records_tool_failed(self):
        registry = ToolRegistry()
        registry.register(FakeFailingTool())
        trace = FakeTrace()

        gateway = ToolGateway(
            tool_registry=registry,
            allowed_tools=["failing_tool"],
            trace=trace,
        )

        with self.assertRaises(RuntimeError):
            gateway.run_tool("failing_tool")

        event_types = [
            event["event_type"]
            for event in trace.events
        ]

        self.assertIn("tool_failed", event_types)

    def test_returns_needs_approval_without_calling_tool(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        trace = FakeTrace()

        gateway = ToolGateway(
            tool_registry=registry,
            allowed_tools=["fake_tool"],
            trace=trace,
            approval_gate=FakeApprovalGate(),
        )

        result = gateway.run_tool("fake_tool", text="danger")

        self.assertTrue(result["needs_approval"])
        self.assertEqual(result["tool_name"], "fake_tool")
        self.assertNotIn("echo", result)
        self.assertIn(
            "tool_needs_approval",
            [event["event_type"] for event in trace.events],
        )


if __name__ == "__main__":
    unittest.main()
