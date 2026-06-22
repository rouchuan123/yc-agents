import unittest
import json

from pathlib import Path

from yc_agents.harness.runtime import YCAgentRuntime, ResearchAgentHarness
from yc_agents.tools.base import BaseTool
from yc_agents.tools.registry import ToolRegistry
from yc_agents.desktop.run_controller import RunController


class FakeAgent:
    def run(self, user_input):
        return f"echo: {user_input}"


class RecordingAgent:
    def __init__(self):
        self.inputs = []

    def run(self, user_input):
        self.inputs.append(user_input)
        return f"echo: {user_input}"


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


class StepController:
    def __init__(self, cancel_on=None, redirects=None):
        self.run_id = "run_001"
        self.cancelled = False
        self.paused = False
        self.cancel_on = cancel_on
        self.redirects = list(redirects or [])
        self.checks = []

    def wait_if_paused(self):
        self.checks.append("wait")

    def raise_if_cancelled(self, checkpoint):
        self.checks.append(checkpoint)
        if checkpoint == self.cancel_on:
            self.cancelled = True
            raise RuntimeError("cancelled")

    def pop_redirects(self):
        redirects = list(self.redirects)
        self.redirects.clear()
        return redirects


class LateRedirectController:
    def __init__(self):
        self.run_id = "run_001"
        self.cancelled = False
        self.paused = False
        self.redirects = []
        self.checks = []

    def wait_if_paused(self):
        pass

    def raise_if_cancelled(self, checkpoint):
        self.checks.append(checkpoint)
        if checkpoint == "before_final_write":
            self.redirects.append("只列目录")

    def pop_redirects(self):
        redirects = list(self.redirects)
        self.redirects.clear()
        return redirects


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

    def test_old_research_harness_name_still_works(self):
        runtime = ResearchAgentHarness(FakeAgent())

        response = runtime.run("hello")

        self.assertEqual(response, "echo: hello")

    def test_runtime_writes_run_outputs(self):
        runtime = YCAgentRuntime(FakeAgent())
        runs_dir = Path("outputs/runs")
        before = set(runs_dir.iterdir()) if runs_dir.exists() else set()

        runtime.run("check files")

        after = set(runs_dir.iterdir())
        new_runs = list(after - before)
        self.assertEqual(len(new_runs), 1)
        latest_run = new_runs[0]

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

    def test_runtime_cancel_before_model_call_stops_agent(self):
        agent = FakeAgent()
        runtime = YCAgentRuntime(agent)
        controller = StepController(cancel_on="before_model_call")

        with self.assertRaises(RuntimeError):
            runtime.run("hello", controller=controller)

        self.assertIn("before_model_call", controller.checks)

    def test_runtime_injects_redirects_before_model_call(self):
        agent = FakeAgent()
        runtime = YCAgentRuntime(agent)
        controller = StepController(redirects=["只列目录"])

        response = runtime.run("写开题报告", controller=controller)

        self.assertEqual(response, "echo: 写开题报告\n\n用户中途改方向：\n只列目录")

    def test_runtime_injects_redirects_before_final_write(self):
        agent = RecordingAgent()
        runtime = YCAgentRuntime(agent)
        controller = LateRedirectController()

        response = runtime.run("写开题报告", controller=controller)

        redirected_prompt = "写开题报告\n\n用户中途改方向：\n只列目录"
        self.assertEqual(agent.inputs, ["写开题报告", redirected_prompt])
        self.assertEqual(response, f"echo: {redirected_prompt}")

    def test_runtime_checks_controller_around_tool_call_and_final_write(self):
        registry = ToolRegistry()
        registry.register(FakeTool())
        runtime = YCAgentRuntime(
            FakeToolCallAgent(),
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["fake_tool"],
        )
        controller = StepController()

        runtime.run("trigger tool", controller=controller)

        self.assertIn("before_tool_call", controller.checks)
        self.assertIn("after_tool_call", controller.checks)
        self.assertIn("before_final_write", controller.checks)


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
