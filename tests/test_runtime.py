import unittest
import json
import tempfile

from pathlib import Path

from yc_agents.harness.runtime import YCAgentRuntime, ResearchAgentHarness
from yc_agents.tools.base import BaseTool
from yc_agents.tools.registry import ToolRegistry


class FakeAgent:
    def run(self, user_input):
        return f"echo: {user_input}"


class FailingAgent:
    def run(self, user_input):
        raise RuntimeError("agent exploded")


class FakeStreamingAgent:
    def __init__(self):
        self.stream_calls = []
        self.run_calls = []
        self.remembered_turns = []

    def stream(self, user_input):
        self.stream_calls.append(user_input)
        yield "hello"
        yield " world"

    def run(self, user_input):
        self.run_calls.append(user_input)
        return "fallback"

    def remember_turn(self, user_input, response):
        self.remembered_turns.append((user_input, response))


class FailingStreamingAgent:
    def stream(self, user_input):
        yield "before failure"
        raise RuntimeError("stream exploded")


class FakeStreamingToolCallAgent:
    def __init__(self):
        self.stream_calls = []
        self.run_calls = []
        self.observation = None

    def stream(self, user_input):
        self.stream_calls.append(user_input)
        yield '{"type":"tool_call",'
        yield '"tool_name":"fake_tool",'
        yield '"arguments":{"text":"danger"},'
        yield '"reason":"test approval gate"}'

    def run(self, user_input):
        self.run_calls.append(user_input)
        return "fallback"

    def run_with_observation(self, user_input, observation):
        self.observation = observation
        return json.dumps(
            {
                "type": "final_answer",
                "content": "approval handled",
            }
        )


class FakeWhitespacePrefixedToolCallAgent(FakeStreamingToolCallAgent):
    def stream(self, user_input):
        self.stream_calls.append(user_input)
        yield "\n  "
        yield '{"type":"tool_call",'
        yield '"tool_name":"fake_tool",'
        yield '"arguments":{"text":"danger"},'
        yield '"reason":"test approval gate"}'


class FakeToolCallAgent:
    def run(self, user_input):
        return json.dumps(
            {
                "type": "tool_call",
                "tool_name": "fake_tool",
                "arguments": {
                    "text": "danger",
                },
                "reason": "test approval gate",
            }
        )

    def run_with_observation(self, user_input, observation):
        return json.dumps(
            {
                "type": "final_answer",
                "content": "approval handled",
            }
        )


class FakeTool(BaseTool):
    name = "fake_tool"
    description = "Fake tool."

    def run(self, text):
        return {
            "echo": text,
        }


class SchemaTool(BaseTool):
    name = "schema_tool"
    description = "Schema tool."

    from yc_agents.harness.tool_schema import ToolField, ToolSchema

    schema = ToolSchema(fields=[ToolField(name="query", type="str", required=True)])

    def run(self, query):
        return {"query": query}


class FakeSchemaToolCallAgent:
    def __init__(self):
        self.observation = None

    def run(self, user_input):
        return json.dumps(
            {
                "type": "tool_call",
                "tool_name": "schema_tool",
                "arguments": {"wrong": "x"},
                "reason": "test validation",
            }
        )

    def run_with_observation(self, user_input, observation):
        self.observation = observation
        return json.dumps(
            {
                "type": "final_answer",
                "content": "validation handled",
            }
        )


class FakeApprovalGate:
    def check_tool_call(self, tool_name, arguments):
        return {
            "allowed": False,
            "needs_approval": True,
            "action": "tool_call",
            "tool_name": tool_name,
            "reason": "approval required",
        }


class TestYCAgentRuntime(unittest.TestCase):
    def test_runtime_runs_agent_and_returns_response(self):
        runtime = YCAgentRuntime(FakeAgent())

        response = runtime.run("hello")

        self.assertEqual(response, "echo: hello")

    def test_runtime_stream_yields_agent_chunks_and_remembers_final_response(self):
        agent = FakeStreamingAgent()
        runtime = YCAgentRuntime(agent)

        chunks = list(runtime.stream("hello"))

        self.assertEqual(chunks, ["hello", " world"])
        self.assertEqual(agent.stream_calls, ["hello"])
        self.assertEqual(agent.run_calls, [])
        self.assertEqual(agent.remembered_turns, [("hello", "hello world")])

    def test_runtime_stream_with_json_protocol_still_yields_non_json_chunks(self):
        agent = FakeStreamingAgent()
        runtime = YCAgentRuntime(agent, expects_json=True)

        chunks = list(runtime.stream("hello"))

        self.assertEqual(chunks, ["hello", " world"])
        self.assertEqual(agent.stream_calls, ["hello"])
        self.assertEqual(agent.run_calls, [])

    def test_runtime_stream_falls_back_to_single_run_response(self):
        runtime = YCAgentRuntime(FakeAgent())

        chunks = list(runtime.stream("hello"))

        self.assertEqual(chunks, ["echo: hello"])

    def test_runtime_stream_buffers_json_tool_calls_until_final_answer(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        runtime = YCAgentRuntime(
            FakeStreamingToolCallAgent(),
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
        )

        chunks = list(runtime.stream("trigger tool"))

        self.assertEqual(chunks, ["approval handled"])
        self.assertNotIn("tool_call", "".join(chunks))
        self.assertEqual(runtime.agent.stream_calls, ["trigger tool"])
        self.assertEqual(runtime.agent.run_calls, [])

    def test_runtime_emits_tool_events_to_callback(self):
        events = []
        registry = ToolRegistry()
        registry.register(FakeTool())
        runtime = YCAgentRuntime(
            FakeStreamingToolCallAgent(),
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
            event_callback=events.append,
        )

        chunks = list(runtime.stream("trigger tool"))

        self.assertEqual(chunks, ["approval handled"])
        event_types = [event["event_type"] for event in events]
        self.assertIn("tool_call_requested", event_types)
        self.assertIn("tool_called", event_types)

    def test_runtime_stream_buffers_whitespace_prefixed_json_tool_calls(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        runtime = YCAgentRuntime(
            FakeWhitespacePrefixedToolCallAgent(),
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
        )

        chunks = list(runtime.stream("trigger tool"))

        self.assertEqual(chunks, ["approval handled"])
        self.assertNotIn("tool_call", "".join(chunks))

    def test_old_research_harness_name_still_works(self):
        runtime = ResearchAgentHarness(FakeAgent())

        response = runtime.run("hello")

        self.assertEqual(response, "echo: hello")

    def test_runtime_writes_run_outputs(self):
        runtime = YCAgentRuntime(FakeAgent())

        runtime.run("check files")

        runs_dir = Path("outputs/runs")
        run_dirs = sorted(runs_dir.iterdir())

        latest_run = run_dirs[-1]

        self.assertTrue((latest_run / "input.md").exists())
        self.assertTrue((latest_run / "final_output.md").exists())
        self.assertTrue((latest_run / "trace.json").exists())

    def test_runtime_writes_episode_context_verification_and_state(self):
        runtime = YCAgentRuntime(FakeAgent())
        runs_dir = Path("outputs/runs")
        before = set(runs_dir.iterdir()) if runs_dir.exists() else set()

        runtime.run("check enhanced episode")

        after = set(runs_dir.iterdir())
        new_runs = list(after - before)
        self.assertEqual(len(new_runs), 1)
        run_dir = new_runs[0]

        self.assertTrue((run_dir / "context.json").exists())
        self.assertTrue((run_dir / "verification.md").exists())
        self.assertTrue((run_dir / "state.json").exists())

        context_data = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
        state_data = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(context_data["run_id"], run_dir.name)
        self.assertEqual(state_data["status"], "finished")

    def test_runtime_passes_approval_gate_to_tool_gateway(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        runtime = YCAgentRuntime(
            FakeToolCallAgent(),
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
            approval_gate=FakeApprovalGate(),
        )
        runs_dir = Path("outputs/runs")
        before = set(runs_dir.iterdir()) if runs_dir.exists() else set()

        response = runtime.run("trigger approval")

        after = set(runs_dir.iterdir())
        new_runs = list(after - before)
        trace = json.loads((new_runs[0] / "trace.json").read_text(encoding="utf-8"))
        event_types = [event["event_type"] for event in trace["events"]]
        self.assertEqual(response, "approval handled")
        self.assertIn("tool_needs_approval", event_types)

    def test_runtime_sends_structured_tool_failure_to_agent(self):
        registry = ToolRegistry()
        registry.register(SchemaTool())
        agent = FakeSchemaToolCallAgent()
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["schema_tool"],
        )

        response = runtime.run("trigger validation")

        self.assertEqual(response, "validation handled")
        self.assertFalse(agent.observation["tool_result"]["ok"])
        self.assertEqual(
            agent.observation["tool_result"]["error_type"],
            "validation_error",
        )

    def test_runtime_records_failed_state_and_trace_when_agent_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = YCAgentRuntime(FailingAgent(), output_root=Path(tmp_dir))

            with self.assertRaises(RuntimeError):
                runtime.run("fail")

            run_dirs = list(Path(tmp_dir).iterdir())
            self.assertEqual(len(run_dirs), 1)
            state = json.loads((run_dirs[0] / "state.json").read_text(encoding="utf-8"))
            trace = json.loads((run_dirs[0] / "trace.json").read_text(encoding="utf-8"))

            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["current_step"], "run_failed")
            self.assertEqual(trace["events"][-1]["event_type"], "run_failed")

    def test_runtime_stream_records_failed_state_and_trace_when_stream_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = YCAgentRuntime(FailingStreamingAgent(), output_root=Path(tmp_dir))

            with self.assertRaises(RuntimeError):
                list(runtime.stream("fail"))

            run_dirs = list(Path(tmp_dir).iterdir())
            self.assertEqual(len(run_dirs), 1)
            state = json.loads((run_dirs[0] / "state.json").read_text(encoding="utf-8"))
            trace = json.loads((run_dirs[0] / "trace.json").read_text(encoding="utf-8"))

            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["current_step"], "run_failed")
            self.assertEqual(trace["events"][-1]["event_type"], "run_failed")


class FakeJSONAgent:
    def run(self, user_input):
        return (
            '{"type":"skill_selection",'
            '"selected_skill":"opening-report",'
            '"confidence":0.9,'
            '"reason":"用户正在准备开题"}'
        )


class FakeInvalidJSONAgent:
    def run(self, user_input):
        return "我觉得应该用 opening-report"


def _run_and_read_trace(runtime, user_input):
    runs_dir = Path("outputs/runs")
    before = set(runs_dir.iterdir()) if runs_dir.exists() else set()

    runtime.run(user_input)

    after = set(runs_dir.iterdir())
    new_runs = list(after - before)

    if len(new_runs) != 1:
        raise AssertionError(f"Expected 1 new run directory, got {len(new_runs)}")

    trace_path = new_runs[0] / "trace.json"

    with trace_path.open("r", encoding="utf-8") as f:
        return json.load(f)


class TestYCAgentRuntimeJSONProtocol(unittest.TestCase):
    def test_runtime_records_skill_selected_for_valid_json(self):
        runtime = YCAgentRuntime(FakeJSONAgent(), expects_json=True)

        trace_data = _run_and_read_trace(runtime, "帮我准备开题")
        event_types = [
            event["event_type"]
            for event in trace_data["events"]
        ]

        self.assertIn("skill_selected", event_types)

    def test_runtime_records_invalid_model_json(self):
        runtime = YCAgentRuntime(FakeInvalidJSONAgent(), expects_json=True)

        trace_data = _run_and_read_trace(runtime, "帮我准备开题")
        event_types = [
            event["event_type"]
            for event in trace_data["events"]
        ]

        self.assertIn("invalid_model_json", event_types)


if __name__ == "__main__":
    unittest.main()
