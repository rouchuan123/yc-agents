import json
import tempfile
import unittest
from pathlib import Path

from yc_agents.harness.json_protocol import InvalidModelJSONError
from yc_agents.harness.runtime import ResearchAgentHarness, YCAgentRuntime
from yc_agents.harness.tool_policy import ToolExecutionPolicy
from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.memory.session import SessionMemory
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


class FakeStreamingPrefaceToolCallAgent:
    def __init__(self):
        self.observations = []
        self.remembered_structured_turns = []

    def stream(self, user_input):
        yield "我先查看项目文件。\n\n"
        yield json.dumps(
            {
                "type": "tool_call",
                "message": "先扫描工作区文件。",
                "tool_name": "fake_tool",
                "arguments": {"text": "list files"},
                "reason": "inspect files",
            }
        )

    def run_with_observation(self, user_input, observation):
        self.observations.append(observation)
        return json.dumps(
            {
                "type": "final_answer",
                "content": "项目分析完成。",
            }
        )

    def remember_structured_turn(self, user_input, response, process_entries):
        self.remembered_structured_turns.append(
            {
                "user_input": user_input,
                "response": response,
                "process_entries": process_entries,
            }
        )


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


class FakeToolThenPlainFinalAgent(FakeToolCallAgent):
    def run_with_observation(self, user_input, observation):
        return json.dumps(
            {
                "type": "final_answer",
                "content": (
                    "## Project review\n\n"
                    "The tool result is enough to answer now."
                ),
            }
        )


class FakeToolThenTruncatedFinalAnswerAgent(FakeToolCallAgent):
    def run_with_observation(self, user_input, observation):
        return (
            '{"type":"final_answer","content":"## Project review\\n\\n'
            "The provider truncated this long Markdown answer before closing the JSON string."
        )


class FakeToolThenMalformedToolCallAgent(FakeToolCallAgent):
    def run_with_observation(self, user_input, observation):
        return '{"type":"tool_call","tool_name":"fake_tool","arguments":'


class FakeProgressToolCallAgent:
    def __init__(self):
        self.remembered_structured_turns = []

    def run(self, user_input):
        return json.dumps(
            {
                "type": "tool_call",
                "message": "我先查看项目文件。",
                "tool_name": "fake_tool",
                "arguments": {"text": "list files"},
                "reason": "inspect files",
            }
        )

    def run_with_observation(self, user_input, observation):
        return json.dumps(
            {
                "type": "final_answer",
                "content": "项目分析完成。",
            }
        )

    def remember_structured_turn(self, user_input, response, process_entries):
        self.remembered_structured_turns.append(
            {
                "user_input": user_input,
                "response": response,
                "process_entries": process_entries,
            }
        )


class FakePrefaceToolCallAgent(FakeProgressToolCallAgent):
    def run(self, user_input):
        return (
            "我先查看项目文件。\n\n"
            + json.dumps(
                {
                    "type": "tool_call",
                    "tool_name": "fake_tool",
                    "arguments": {"text": "list files"},
                    "reason": "inspect files",
                }
            )
        )


class FakeFollowUpPrefaceToolCallAgent(FakeProgressToolCallAgent):
    def __init__(self):
        super().__init__()
        self.observations = []

    def run_with_observation(self, user_input, observation):
        self.observations.append(observation)
        if len(self.observations) == 1:
            return (
                "我接着读取关键文件。\n\n"
                + json.dumps(
                    {
                        "type": "tool_call",
                        "tool_name": "fake_tool",
                        "arguments": {"text": "read README"},
                        "reason": "inspect readme",
                    }
                )
            )
        return json.dumps(
            {
                "type": "final_answer",
                "content": "项目分析完成。",
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


class FakeRuntimeSkillSelectionThenFinalAgent:
    def __init__(self):
        self.repairs = []

    def run(self, user_input):
        return json.dumps(
            {
                "type": "skill_selection",
                "selected_skill": None,
                "confidence": 0.1,
                "reason": "wrong phase",
            }
        )

    def run_with_protocol_error(self, user_input, error, expectation=None):
        self.repairs.append(
            {
                "error": str(error),
                "expectation": expectation,
            }
        )
        return json.dumps({"type": "final_answer", "content": "repaired"})


class FakeMalformedPlainAnswerThenRepairAgent:
    def __init__(self):
        self.repairs = []

    def run(self, user_input):
        return '{"type":"plain_answer","content":"I am not the "model"."}'

    def run_with_protocol_error(self, user_input, error, expectation=None):
        self.repairs.append((str(error), expectation))
        return json.dumps(
            {
                "type": "final_answer",
                "content": 'I am not the "model"; I am YCore.',
            }
        )


class DeepSeekShapedRepairLLM:
    def __init__(self):
        self.calls = 0

    def think_json(self, messages, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return (
                '{"type":"skill_selection","selected_skill":null,'
                '"confidence":0.1,"reason":"simple identity question"}'
            )
        if self.calls == 2:
            return "Hello! I am YCore."
        return '{"type":"final_answer","content":"Hello! I am YCore."}'

    def think(self, messages, **kwargs):
        return self.think_json(messages, **kwargs)


class FakeInvalidJSONAgent:
    def run(self, user_input):
        return "I think code-review is useful"


class FakeInvalidThenFinalAgent:
    def __init__(self):
        self.calls = 0
        self.remembered = []

    def run(self, user_input):
        self.calls += 1
        if self.calls == 1:
            return "not json"
        return json.dumps({"type": "final_answer", "content": "recovered"})

    def run_with_protocol_error(self, user_input, error, expectation=None):
        return self.run(user_input)

    def remember_structured_turn(self, user_input, response, process_entries):
        self.remembered.append((user_input, response, process_entries))


class FakeAlwaysInvalidAgent:
    def __init__(self):
        self.calls = 0
        self.remembered = []

    def run(self, user_input):
        self.calls += 1
        return "still not json"

    def run_with_protocol_error(self, user_input, error, expectation=None):
        return self.run(user_input)

    def remember_structured_turn(self, user_input, response, process_entries):
        self.remembered.append((user_input, response, process_entries))


class FakeTool(BaseTool):
    name = "fake_tool"
    description = "Fake tool."

    def run(self, text):
        return {"echo": text}


class FakeRunAnalytics:
    def __init__(self):
        self.events = []
        self.verifications = []
        self.outputs = []
        self.finishes = []
        self.strict = True

    def record_event(self, event):
        self.events.append(event)

    def record_verification(self, verification):
        self.verifications.append(verification)

    def record_final_output(self, output):
        self.outputs.append(output)

    def finish(self, status, finished_at=None, error_type=None, error_message=None):
        self.finishes.append(
            {
                "status": status,
                "error_type": error_type,
                "error_message": error_message,
            }
        )


class FakeAnalyticsRecorder:
    def __init__(self):
        self.started = []
        self.run = FakeRunAnalytics()
        self.closed = False

    def start_run(self, context):
        self.started.append(context.run_id)
        return self.run

    def close(self):
        self.closed = True


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

    def test_streaming_json_runtime_executes_prefixed_tool_call(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        agent = FakeStreamingPrefaceToolCallAgent()
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
        )

        chunks = list(runtime.stream("analyze project"))

        self.assertEqual(chunks, ["项目分析完成。"])
        self.assertEqual(len(agent.observations), 1)
        self.assertEqual(agent.observations[0]["tool_result"], {"echo": "list files"})
        process_entries = agent.remembered_structured_turns[0]["process_entries"]
        self.assertEqual(process_entries[0]["content"], "我先查看项目文件。")
        self.assertEqual(process_entries[1]["content"], "先扫描工作区文件。")

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

    def test_runtime_accepts_final_answer_json_after_tool_observation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ToolRegistry()
            registry.register(FakeTool())
            runtime = YCAgentRuntime(
                FakeToolThenPlainFinalAgent(),
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["fake_tool"],
                fail_on_invalid_json=True,
                output_root=Path(tmp_dir),
            )

            response = runtime.run("trigger tool")
            run_dir = next(Path(tmp_dir).iterdir())
            trace = json.loads((run_dir / "trace.json").read_text(encoding="utf-8"))

            self.assertIn("## Project review", response)
            self.assertIn("The tool result is enough to answer now.", response)
            self.assertNotIn(
                "invalid_model_json",
                [event["event_type"] for event in trace["events"]],
            )

    def test_runtime_rejects_truncated_final_answer_json_after_tool_observation(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        runtime = YCAgentRuntime(
            FakeToolThenTruncatedFinalAnswerAgent(),
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
            fail_on_invalid_json=True,
        )

        with self.assertRaises(InvalidModelJSONError):
            runtime.run("trigger tool")

    def test_runtime_still_rejects_malformed_tool_call_after_observation(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        runtime = YCAgentRuntime(
            FakeToolThenMalformedToolCallAgent(),
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
            fail_on_invalid_json=True,
        )

        with self.assertRaises(InvalidModelJSONError):
            runtime.run("trigger tool")

    def test_runtime_collects_progress_message_and_tool_summary(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        agent = FakeProgressToolCallAgent()
        events = []
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
            event_callback=events.append,
        )

        response = runtime.run("analyze project")

        self.assertEqual(response, "项目分析完成。")
        process_entries = agent.remembered_structured_turns[0]["process_entries"]
        self.assertEqual(
            process_entries[0],
            {"type": "assistant_step", "content": "我先查看项目文件。"},
        )
        self.assertEqual(process_entries[1]["type"], "tool_call")
        self.assertEqual(process_entries[1]["tool_name"], "fake_tool")
        self.assertEqual(process_entries[2]["type"], "tool_result")
        self.assertEqual(process_entries[2]["summary"], "工具执行完成。")
        self.assertIn("assistant_process", [event["event_type"] for event in events])

    def test_runtime_extracts_preface_before_tool_json_as_progress_message(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        agent = FakePrefaceToolCallAgent()
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
        )

        response = runtime.run("analyze project")

        self.assertEqual(response, "项目分析完成。")
        self.assertEqual(
            agent.remembered_structured_turns[0]["process_entries"][0],
            {"type": "assistant_step", "content": "我先查看项目文件。"},
        )

    def test_runtime_continues_after_prefixed_follow_up_tool_call(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        agent = FakeFollowUpPrefaceToolCallAgent()
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
        )

        response = runtime.run("analyze project")

        self.assertEqual(response, "项目分析完成。")
        self.assertEqual(len(agent.observations), 2)
        self.assertEqual(
            [item["tool_result"]["echo"] for item in agent.observations],
            ["list files", "read README"],
        )
        self.assertIn(
            {"type": "assistant_step", "content": "我接着读取关键文件。"},
            agent.remembered_structured_turns[0]["process_entries"],
        )

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

    def test_runtime_rejects_skill_selection_response_and_repairs_to_final_answer(self):
        agent = FakeRuntimeSkillSelectionThenFinalAgent()
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            invalid_json_retry_count=1,
            fail_on_invalid_json=True,
        )

        response = runtime.run("hello")

        self.assertEqual(response, "repaired")
        self.assertEqual(
            agent.repairs[0]["expectation"]["allowed_types"],
            ["final_answer", "tool_call"],
        )

    def test_runtime_repairs_malformed_plain_answer_json(self):
        agent = FakeMalformedPlainAnswerThenRepairAgent()
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            invalid_json_retry_count=1,
            fail_on_invalid_json=True,
        )

        response = runtime.run("what model are you")

        self.assertIn('I am not the "model"', response)
        self.assertTrue(agent.repairs)

    def test_deepseek_shaped_plain_text_runtime_response_repairs_to_final_answer(self):
        llm = DeepSeekShapedRepairLLM()
        agent = SkillRuntimeAgent(llm, session_memory=SessionMemory())
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            invalid_json_retry_count=1,
            fail_on_invalid_json=True,
        )

        response = runtime.run("what model are you")

        self.assertEqual(response, "Hello! I am YCore.")
        self.assertEqual(llm.calls, 3)
        self.assertEqual(
            [event["event_type"] for event in runtime.last_trace_events].count(
                "invalid_model_json"
            ),
            1,
        )

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

    def test_runtime_retries_invalid_json_once_and_recovers(self):
        agent = FakeInvalidThenFinalAgent()
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            invalid_json_retry_count=1,
            fail_on_invalid_json=True,
        )

        response = runtime.run("recover")

        self.assertEqual(response, "recovered")
        self.assertEqual(agent.calls, 2)
        self.assertTrue(agent.remembered)

    def test_runtime_marks_run_failed_when_invalid_json_persists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            agent = FakeAlwaysInvalidAgent()
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                output_root=Path(tmp_dir),
                invalid_json_retry_count=1,
                fail_on_invalid_json=True,
            )

            with self.assertRaises(InvalidModelJSONError):
                runtime.run("fail")

            run_dir = next(Path(tmp_dir).iterdir())
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            trace = json.loads((run_dir / "trace.json").read_text(encoding="utf-8"))

            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["current_step"], "run_failed")
            self.assertEqual(
                [event["event_type"] for event in trace["events"]].count("invalid_model_json"),
                2,
            )
            self.assertEqual(agent.remembered, [])

    def test_runtime_mirrors_events_verification_and_output_to_analytics(self):
        recorder = FakeAnalyticsRecorder()
        runtime = YCAgentRuntime(FakeAgent(), analytics_recorder=recorder)

        response = runtime.run("hello analytics")

        self.assertEqual(response, "echo: hello analytics")
        self.assertTrue(recorder.started)
        self.assertIn(
            "run_started",
            [event["event_type"] for event in recorder.run.events],
        )
        self.assertEqual(recorder.run.outputs, ["echo: hello analytics"])
        self.assertTrue(recorder.run.verifications[0]["passed"])
        self.assertEqual(recorder.run.finishes[-1]["status"], "finished")

    def test_runtime_close_closes_analytics_recorder(self):
        recorder = FakeAnalyticsRecorder()
        runtime = YCAgentRuntime(FakeAgent(), analytics_recorder=recorder)

        runtime.close()

        self.assertTrue(recorder.closed)


if __name__ == "__main__":
    unittest.main()
