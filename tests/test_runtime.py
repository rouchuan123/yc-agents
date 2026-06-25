import json
import tempfile
import unittest
from pathlib import Path

from yc_agents.harness.runtime import ResearchAgentHarness, YCAgentRuntime
from yc_agents.harness.tool_policy import ToolExecutionPolicy
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


class FakeToolCallAgent:
    def run(self, user_input):
        return json.dumps(
            {
                "type": "tool_call",
                "tool_name": "fake_tool",
                "arguments": {"text": "draft.docx"},
                "reason": "test tool call",
            }
        )

    def run_with_observation(self, user_input, observation):
        return json.dumps(
            {
                "type": "final_answer",
                "content": "tool handled",
            }
        )


class FakeMultiToolCallAgent:
    def __init__(self):
        self.observations = []

    def run(self, user_input):
        return json.dumps(
            {
                "type": "tool_call",
                "tool_name": "fake_tool",
                "arguments": {"text": "list files"},
                "reason": "first tool call",
            }
        )

    def run_with_observation(self, user_input, observation):
        self.observations.append(observation)
        if len(self.observations) == 1:
            return json.dumps(
                {
                    "type": "tool_call",
                    "tool_name": "fake_tool",
                    "arguments": {"text": "summarize risks"},
                    "reason": "second tool call",
                }
            )
        return json.dumps(
            {
                "type": "final_answer",
                "content": "review complete",
            }
        )


class FakeLoopingToolCallAgent:
    def __init__(self):
        self.observations = []

    def run(self, user_input):
        return self._tool_call()

    def run_with_observation(self, user_input, observation):
        self.observations.append(observation)
        return self._tool_call()

    def _tool_call(self):
        return json.dumps(
            {
                "type": "tool_call",
                "tool_name": "fake_tool",
                "arguments": {"text": "repeat"},
                "reason": "loop",
            }
        )


class FakeSkillSelectionAgent:
    def run(self, user_input):
        return json.dumps(
            {
                "type": "skill_selection",
                "selected_skill": "code-review",
                "confidence": 0.9,
                "reason": "project review",
            }
        )


class FakeInvalidJSONAgent:
    def run(self, user_input):
        return "I think code-review is useful"


class FakeTool(BaseTool):
    name = "fake_tool"
    description = "Fake tool."

    def run(self, text):
        return {"echo": text}


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

    def test_runtime_stream_falls_back_to_single_run_response(self):
        runtime = YCAgentRuntime(FakeAgent())

        chunks = list(runtime.stream("hello"))

        self.assertEqual(chunks, ["echo: hello"])

    def test_old_research_harness_name_still_works(self):
        runtime = ResearchAgentHarness(FakeAgent())

        response = runtime.run("hello")

        self.assertEqual(response, "echo: hello")

    def test_runtime_writes_episode_context_verification_and_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = YCAgentRuntime(FakeAgent(), output_root=Path(tmp_dir))

            runtime.run("check outputs")

            run_dirs = list(Path(tmp_dir).iterdir())
            self.assertEqual(len(run_dirs), 1)
            run_dir = run_dirs[0]
            self.assertTrue((run_dir / "input.md").exists())
            self.assertTrue((run_dir / "final_output.md").exists())
            self.assertTrue((run_dir / "trace.json").exists())
            self.assertTrue((run_dir / "context.json").exists())
            self.assertTrue((run_dir / "verification.md").exists())
            self.assertTrue((run_dir / "state.json").exists())

    def test_runtime_handles_json_tool_call_and_final_answer(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        runtime = YCAgentRuntime(
            FakeToolCallAgent(),
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
        )

        response = runtime.run("trigger tool")

        self.assertEqual(response, "tool handled")

    def test_runtime_handles_multiple_json_tool_calls_before_final_answer(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ToolRegistry()
            registry.register(FakeTool())
            agent = FakeMultiToolCallAgent()
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["fake_tool"],
                output_root=Path(tmp_dir),
            )

            response = runtime.run("trigger multiple tools")

            run_dir = next(Path(tmp_dir).iterdir())
            trace = json.loads((run_dir / "trace.json").read_text(encoding="utf-8"))
            event_types = [event["event_type"] for event in trace["events"]]
            self.assertEqual(response, "review complete")
            self.assertEqual(len(agent.observations), 2)
            self.assertEqual(
                [item["tool_result"]["echo"] for item in agent.observations],
                ["list files", "summarize risks"],
            )
            self.assertEqual(event_types.count("tool_call_requested"), 2)
            self.assertEqual(event_types.count("tool_called"), 2)

    def test_runtime_returns_user_visible_message_when_tool_loop_limit_stops(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        agent = FakeLoopingToolCallAgent()
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
            tool_policy=ToolExecutionPolicy(max_calls=1, max_repeated_calls=1),
        )

        response = runtime.run("trigger loop limit")

        self.assertIn("工具调用次数过多", response)
        self.assertIn("已停止", response)
        self.assertEqual(len(agent.observations), 1)

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

        response = runtime.run("trigger approval")

        self.assertEqual(response, "tool handled")

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

    def test_runtime_records_skill_selected_for_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = YCAgentRuntime(
                FakeSkillSelectionAgent(),
                expects_json=True,
                output_root=Path(tmp_dir),
            )

            runtime.run("review this project")

            run_dir = next(Path(tmp_dir).iterdir())
            trace = json.loads((run_dir / "trace.json").read_text(encoding="utf-8"))
            event_types = [event["event_type"] for event in trace["events"]]
            self.assertIn("skill_selected", event_types)

    def test_runtime_records_invalid_model_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = YCAgentRuntime(
                FakeInvalidJSONAgent(),
                expects_json=True,
                output_root=Path(tmp_dir),
            )

            runtime.run("review this project")

            run_dir = next(Path(tmp_dir).iterdir())
            trace = json.loads((run_dir / "trace.json").read_text(encoding="utf-8"))
            event_types = [event["event_type"] for event in trace["events"]]
            self.assertIn("invalid_model_json", event_types)


if __name__ == "__main__":
    unittest.main()
