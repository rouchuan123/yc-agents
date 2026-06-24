from pathlib import Path

from yc_agents.harness.resume import ResumePoint
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.harness.state import StateStore


class FakeAgent:
    def __init__(self):
        self.inputs = []

    def run(self, user_input):
        self.inputs.append(user_input)
        return f"echo: {user_input}"


def test_resume_point_serializes_document_format_skill():
    point = ResumePoint(
        run_id="run-1",
        status="failed",
        last_step="tool_call",
        user_input="调整 draft.docx 格式",
        selected_skill="document-format-normalizer",
        redirect_instruction="改用 report-standard",
    )

    data = point.to_dict()

    assert data["selected_skill"] == "document-format-normalizer"
    assert data["redirect_instruction"] == "改用 report-standard"


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
        {"user_input": "调整 draft.docx 格式"},
    )
    agent = FakeAgent()
    runtime = YCAgentRuntime(agent)

    response = runtime.resume_from_state(
        state_path,
        redirect_instruction="改用 report-standard",
    )

    assert response.startswith("echo: 调整 draft.docx 格式")
    assert "改用 report-standard" in agent.inputs[0]
