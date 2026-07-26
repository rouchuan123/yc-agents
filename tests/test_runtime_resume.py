import json
from pathlib import Path

from yc_agents.harness.resume import ResumePoint
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.harness.state import StateStore
from yc_agents.tools.base import BaseTool
from yc_agents.tools.registry import ToolRegistry


class FakeAgent:
    def __init__(self):
        self.inputs = []

    def run(self, user_input):
        self.inputs.append(user_input)
        return f"echo: {user_input}"


class EchoTool(BaseTool):
    name = "fake_tool"
    description = "Fake tool."

    def run(self, text):
        return {"echo": text}


class ResumeObservationAgent:
    def __init__(self):
        self.run_calls = []
        self.observations = []

    def run(self, user_input):
        self.run_calls.append(user_input)
        return json.dumps({"type": "final_answer", "content": "full rerun"})

    def run_with_observation(self, user_input, observation):
        self.observations.append((user_input, observation))
        return json.dumps({"type": "final_answer", "content": "resumed answer"})


class ResumeToolThenFinalAgent:
    def __init__(self):
        self.run_calls = []
        self.observations = []

    def run(self, user_input):
        self.run_calls.append(user_input)
        raise AssertionError("resume with steps should not rerun the initial call")

    def run_with_observation(self, user_input, observation):
        self.observations.append(observation)
        if len(self.observations) == 1:
            return json.dumps(
                {
                    "type": "tool_call",
                    "tool_name": "fake_tool",
                    "arguments": {"text": "read README"},
                    "reason": "continue",
                }
            )
        return json.dumps({"type": "final_answer", "content": "resumed with tool"})


def _stopped_tool_loop_state(tmp_path):
    state_path = Path(tmp_path) / "state.json"
    store = StateStore(state_path)
    store.save_checkpoint("run_started", "running", {"user_input": "write the report"})
    store.append_step(
        {
            "index": 0,
            "tool_call": {
                "tool_name": "fake_tool",
                "arguments": {"text": "list files"},
                "reason": "inspect",
            },
            "tool_result": {"echo": "list files"},
            "artifacts": [],
        }
    )
    store.save_checkpoint("run_finished", "failed", {"error": "provider flapping"})
    return state_path


def test_resume_point_serializes_selected_skill():
    point = ResumePoint(
        run_id="run-1",
        status="failed",
        last_step="tool_call",
        user_input="review this project",
        selected_skill="code-review",
        redirect_instruction="focus on testing gaps",
    )

    data = point.to_dict()

    assert data["selected_skill"] == "code-review"
    assert data["redirect_instruction"] == "focus on testing gaps"


def test_resume_from_state_returns_clear_message_without_checkpoint(tmp_path):
    runtime = YCAgentRuntime(FakeAgent())

    response = runtime.resume_from_state(tmp_path / "missing-state.json")

    assert response == "No checkpoint available to resume."


def test_resume_from_state_replays_user_input_with_redirect(tmp_path):
    state_path = Path(tmp_path) / "state.json"
    store = StateStore(state_path)
    store.save_checkpoint(
        "model_called",
        "failed",
        {"user_input": "review this project"},
    )
    agent = FakeAgent()
    runtime = YCAgentRuntime(agent)

    response = runtime.resume_from_state(
        state_path,
        redirect_instruction="focus on testing gaps",
    )

    assert response.startswith("echo: review this project")
    assert "focus on testing gaps" in agent.inputs[0]


def test_resume_from_steps_continues_from_observation_without_full_rerun(tmp_path):
    state_path = _stopped_tool_loop_state(tmp_path)
    agent = ResumeObservationAgent()
    runtime = YCAgentRuntime(
        agent,
        expects_json=True,
        output_root=tmp_path / "resumed-runs",
    )

    response = runtime.resume_from_state(state_path)

    assert response == "resumed answer"
    assert response.status == "finished"
    assert agent.run_calls == []
    user_input, observation = agent.observations[0]
    assert user_input == "write the report"
    assert observation["tool_call"]["tool_name"] == "fake_tool"
    assert observation["tool_result"] == {"echo": "list files"}
    assert observation["execution_history"] == []


def test_resume_from_steps_keeps_redirect_instruction(tmp_path):
    state_path = _stopped_tool_loop_state(tmp_path)
    agent = ResumeObservationAgent()
    runtime = YCAgentRuntime(
        agent,
        expects_json=True,
        output_root=tmp_path / "resumed-runs",
    )

    runtime.resume_from_state(state_path, redirect_instruction="加一节结论")

    user_input, _observation = agent.observations[0]
    assert "write the report" in user_input
    assert "用户追加指令：加一节结论" in user_input


def test_resume_from_steps_continues_tool_loop_and_appends_new_steps(tmp_path):
    state_path = _stopped_tool_loop_state(tmp_path)
    registry = ToolRegistry()
    registry.register(EchoTool())
    agent = ResumeToolThenFinalAgent()
    runtime = YCAgentRuntime(
        agent,
        expects_json=True,
        tool_registry=registry,
        allowed_tools=["fake_tool"],
        output_root=tmp_path / "resumed-runs",
    )

    response = runtime.resume_from_state(state_path)

    assert response == "resumed with tool"
    assert agent.run_calls == []
    assert len(agent.observations) == 2
    assert agent.observations[1]["tool_result"] == {"echo": "read README"}
    steps = StateStore(Path(runtime.last_run_dir) / "state.json").load_steps()
    assert [step["index"] for step in steps] == [0, 1]
    assert steps[1]["tool_call"]["arguments"] == {"text": "read README"}
