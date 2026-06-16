import unittest
import json

from pathlib import Path

from yc_agents.harness.runtime import YCAgentRuntime, ResearchAgentHarness


class FakeAgent:
    def run(self, user_input):
        return f"echo: {user_input}"


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

        runtime.run("check files")

        runs_dir = Path("outputs/runs")
        run_dirs = sorted(runs_dir.iterdir())

        latest_run = run_dirs[-1]

        self.assertTrue((latest_run / "input.md").exists())
        self.assertTrue((latest_run / "final_output.md").exists())
        self.assertTrue((latest_run / "trace.json").exists())


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