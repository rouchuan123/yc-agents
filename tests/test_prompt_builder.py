import json

from yc_agents.prompts.builder import PromptBuilder
from yc_agents.prompts.project_instructions import ProjectInstruction


def make_builder():
    return PromptBuilder(
        project_instructions=[
            ProjectInstruction(
                source="YCORE.md",
                path=None,
                content="Root says prefer concise answers.",
            ),
            ProjectInstruction(
                source=".ycore/YCORE.md",
                path=None,
                content="Local says mention test commands.",
            ),
        ]
    )


def test_plain_answer_messages_include_project_instructions_in_order():
    messages = make_builder().plain_answer_messages(
        user_input="hello",
        memory={"session": [], "summary": "", "profile": {}},
        workspace_context={
            "path": "C:/project",
            "available_tools": ["workspace_files"],
        },
    )

    system_prompt = messages[0]["content"]
    assert system_prompt.index("Root says prefer concise answers.") < system_prompt.index(
        "Local says mention test commands."
    )
    assert "YCORE.md" in system_prompt
    assert ".ycore/YCORE.md" in system_prompt


def test_core_prompt_is_generic_not_word_or_old_domain_specific():
    messages = make_builder().plain_answer_messages(
        user_input="hello",
        memory={"session": [], "summary": "", "profile": {}},
        workspace_context={
            "available_tools": ["workspace_files", "file_reader", "web_search"],
        },
    )

    system_prompt = messages[0]["content"].lower()
    assert "ycore" in system_prompt
    assert "skill-driven" in system_prompt
    assert "web_search" in system_prompt
    assert "workspace_files" in system_prompt
    assert ("docx" + "_format" + "_normalizer") not in system_prompt
    assert "word document automation" not in system_prompt
    assert "论文" not in system_prompt


def test_skill_execution_messages_include_selected_skill_context_as_user_json():
    messages = make_builder().skill_execution_messages(
        context={
            "task": "skill_execution",
            "user_input": "review this project",
            "selected_skill": {"name": "code-review", "body": "Review instructions"},
            "workspace": {"path": "C:/project"},
        }
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    payload = json.loads(messages[1]["content"])
    assert payload["selected_skill"]["name"] == "code-review"
    assert "Review instructions" in messages[1]["content"]


def test_observation_messages_require_tool_call_or_final_answer_json():
    messages = make_builder().observation_messages(
        user_input="list files",
        memory={"session": [], "summary": "", "profile": {}},
        workspace_context={"path": "C:/project"},
        observation={"tool_result": {"files": []}},
    )

    system_prompt = messages[0]["content"]
    assert "Return only valid JSON" in system_prompt
    assert "tool_call" in system_prompt
    assert "final_answer" in system_prompt
    assert "If another tool is needed" in system_prompt
