import unittest
import time

from yc_agents.harness.tool_gateway import ToolGateway, ToolNotAllowedError
from yc_agents.harness.tool_policy import ToolExecutionPolicy, ToolLoopError
from yc_agents.harness.tool_result import ToolExecutionResult
from yc_agents.harness.tool_schema import ToolField, ToolSchema
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


class EventTool(BaseTool):
    name = "event_tool"
    description = "Returns a stable payload."

    def run(self, value="ok"):
        return {"value": value}


class SchemaTool(BaseTool):
    name = "schema_tool"
    description = "A schema tool for tests."
    schema = ToolSchema(fields=[ToolField(name="query", type="str", required=True)])

    def run(self, query):
        return {"query": query}


class FlakyTool(BaseTool):
    name = "flaky"
    description = "A flaky tool for tests."

    def __init__(self):
        self.calls = 0

    def run(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary")
        return "ok"


class SlowTool(BaseTool):
    name = "slow"
    description = "A slow tool for timeout tests."

    def run(self):
        time.sleep(0.2)
        return "too late"


class PermissionFailingTool(BaseTool):
    name = "permission_failing"
    description = "A tool that is denied by the operating system."

    def __init__(self):
        self.calls = 0

    def run(self):
        self.calls += 1
        raise PermissionError("access denied")


class MissingFileTool(BaseTool):
    name = "missing_file"
    description = "A tool that cannot find its input file."

    def __init__(self):
        self.calls = 0

    def run(self):
        self.calls += 1
        raise FileNotFoundError("missing.txt")


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


class ToolRegistryStub:
    def __init__(self, tools):
        self.tools = {tool.name: tool for tool in tools}

    def get_tool(self, name):
        return self.tools[name]


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
        events = []

        gateway = ToolGateway(
            tool_registry=registry,
            allowed_tools=["fake_tool"],
            trace=trace,
            event_callback=events.append,
        )

        gateway.run_tool("fake_tool", "hello")

        event_types = [
            event["event_type"]
            for event in trace.events
        ]

        self.assertIn("tool_called", event_types)
        self.assertIn("tool_called", [event["event_type"] for event in events])

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

        result = gateway.run_tool("failing_tool")

        event_types = [
            event["event_type"]
            for event in trace.events
        ]

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "execution_error")
        self.assertIn("tool_failed", event_types)

    def test_emits_tool_result_event_for_successful_tool(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        events = []
        gateway = ToolGateway(
            tool_registry=registry,
            allowed_tools=["fake_tool"],
            event_callback=events.append,
        )

        gateway.run_tool("fake_tool", "hello")

        tool_result_events = [
            event for event in events if event["event_type"] == "tool_result"
        ]
        self.assertEqual(len(tool_result_events), 1)
        self.assertEqual(tool_result_events[0]["payload"]["tool_name"], "fake_tool")
        self.assertEqual(tool_result_events[0]["payload"]["result"], {"echo": "hello"})

    def test_emits_tool_result_event_for_failed_tool(self):
        registry = ToolRegistry()
        registry.register(FakeFailingTool())
        events = []
        gateway = ToolGateway(
            tool_registry=registry,
            allowed_tools=["failing_tool"],
            event_callback=events.append,
        )

        gateway.run_tool("failing_tool")

        tool_result_events = [
            event for event in events if event["event_type"] == "tool_result"
        ]
        self.assertEqual(len(tool_result_events), 1)
        self.assertEqual(tool_result_events[0]["payload"]["tool_name"], "failing_tool")
        self.assertEqual(tool_result_events[0]["payload"]["result"]["ok"], False)

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

    def test_tool_execution_result_success_dict(self):
        result = ToolExecutionResult.success("rag_search", {"answer": "ok"})

        self.assertTrue(result.to_dict()["ok"])
        self.assertEqual(result.to_dict()["tool_name"], "rag_search")

    def test_tool_execution_result_failure_dict(self):
        result = ToolExecutionResult.failure(
            "rag_search",
            "validation_error",
            "missing query",
        )

        self.assertFalse(result.to_dict()["ok"])
        self.assertEqual(result.to_dict()["error_type"], "validation_error")

    def test_tool_policy_blocks_repeated_call(self):
        policy = ToolExecutionPolicy(max_repeated_calls=1)
        policy.record_call("rag_search", {"query": "abc"})

        with self.assertRaises(ToolLoopError):
            policy.record_call("rag_search", {"query": "abc"})

    def test_tool_policy_blocks_max_calls(self):
        policy = ToolExecutionPolicy(max_calls=1)
        policy.record_call("rag_search", {"query": "abc"})

        with self.assertRaises(ToolLoopError):
            policy.record_call("docx_reader", {"file_path": "a.docx"})

    def test_gateway_returns_structured_validation_error(self):
        registry = ToolRegistry()
        registry.register(SchemaTool())
        trace = FakeTrace()
        gateway = ToolGateway(
            registry,
            allowed_tools=["schema_tool"],
            trace=trace,
        )

        result = gateway.run_tool("schema_tool", wrong="x")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "validation_error")
        self.assertIn(
            "tool_validation_failed",
            [event["event_type"] for event in trace.events],
        )

    def test_gateway_retries_transient_failure(self):
        registry = ToolRegistry()
        tool = FlakyTool()
        registry.register(tool)
        trace = FakeTrace()
        gateway = ToolGateway(
            registry,
            allowed_tools=["flaky"],
            trace=trace,
            policy=ToolExecutionPolicy(max_retries=1),
        )

        result = gateway.run_tool("flaky")

        self.assertEqual(result, "ok")
        self.assertEqual(tool.calls, 2)
        self.assertIn("tool_retry", [event["event_type"] for event in trace.events])

    def test_gateway_returns_timeout_failure(self):
        registry = ToolRegistry()
        registry.register(SlowTool())
        gateway = ToolGateway(
            registry,
            allowed_tools=["slow"],
            policy=ToolExecutionPolicy(timeout_seconds=0.01),
        )

        result = gateway.run_tool("slow")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "timeout")

    def test_gateway_does_not_retry_permission_failure(self):
        registry = ToolRegistry()
        tool = PermissionFailingTool()
        registry.register(tool)
        gateway = ToolGateway(
            registry,
            allowed_tools=[tool.name],
            policy=ToolExecutionPolicy(max_retries=2),
        )

        result = gateway.run_tool(tool.name)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "permission_error")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(tool.calls, 1)

    def test_gateway_does_not_retry_missing_file_failure(self):
        registry = ToolRegistry()
        tool = MissingFileTool()
        registry.register(tool)
        gateway = ToolGateway(
            registry,
            allowed_tools=[tool.name],
            policy=ToolExecutionPolicy(max_retries=2),
        )

        result = gateway.run_tool(tool.name)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "not_found")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(tool.calls, 1)

    def test_tool_gateway_records_denied_event(self):
        events = []
        gateway = ToolGateway(
            ToolRegistryStub([EventTool()]),
            allowed_tools=[],
            event_callback=events.append,
        )

        try:
            gateway.run_tool("event_tool")
        except ToolNotAllowedError:
            pass

        self.assertEqual(events[0]["event_type"], "tool_denied")
        self.assertEqual(events[0]["payload"]["tool_name"], "event_tool")

    def test_tool_gateway_records_validation_failure_result(self):
        events = []
        gateway = ToolGateway(
            ToolRegistryStub([SchemaTool()]),
            allowed_tools=["schema_tool"],
            event_callback=events.append,
        )

        result = gateway.run_tool("schema_tool")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "validation_error")
        self.assertEqual(
            [event["event_type"] for event in events],
            [
                "tool_validation_failed",
                "tool_result",
            ],
        )

    def test_tool_gateway_records_retry_and_failure_events(self):
        events = []
        gateway = ToolGateway(
            ToolRegistryStub([FakeFailingTool()]),
            allowed_tools=["failing_tool"],
            policy=ToolExecutionPolicy(max_retries=1),
            event_callback=events.append,
        )

        result = gateway.run_tool("failing_tool")

        self.assertFalse(result["ok"])
        self.assertEqual(result["attempts"], 2)
        event_types = [event["event_type"] for event in events]
        self.assertIn("tool_retry", event_types)
        self.assertIn("tool_failed", event_types)
        self.assertEqual(event_types[-1], "tool_result")


if __name__ == "__main__":
    unittest.main()
