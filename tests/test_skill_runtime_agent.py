import json
import tempfile
import unittest
from pathlib import Path

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.session import SessionMemory
from yc_agents.prompts.builder import PromptBuilder
from yc_agents.prompts.project_instructions import ProjectInstruction
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.registry import ToolRegistry


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = []
        self.stream_messages = []

    def think(self, messages):
        self.messages.append(messages)
        return self.responses.pop(0)

    def stream_think(self, messages):
        self.stream_messages.append(messages)
        yield from self.responses.pop(0)


class FakeRAGSearchTool:
    def __init__(self):
        self.calls = []

    def run(self, query, top_k=3):
        self.calls.append({"query": query, "top_k": top_k})
        return [{"source": "template.md", "text": "report-standard"}]


def write_skill(skills_dir, name="code-review", allowed_tools=None):
    allowed_tools = allowed_tools or ["markdown_writer"]
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    lines = [
        "---",
        f"name: {name}",
        "description: Use when the user wants a project code review.",
        "allowed_tools:",
    ]
    lines.extend(f"  - {tool}" for tool in allowed_tools)
    lines.extend(
        [
            "---",
            "",
            "# Code Review Skill",
            "",
            "Summarize the project structure, architecture, risks, and test gaps.",
        ]
    )
    skill_file.write_text("\n".join(lines), encoding="utf-8")


class TestSkillRuntimeAgent(unittest.TestCase):
    def test_run_includes_workspace_context_in_model_prompts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            skills_dir = root / "skills"
            workspace = root / "workspace"
            workspace.mkdir()
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": None,
                            "confidence": 0.2,
                            "reason": "plain answer",
                        }
                    ),
                    "Workspace is available.",
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                workspace_context={
                    "path": str(workspace),
                    "name": "workspace",
                    "available_tools": ["workspace_files", "file_reader"],
                },
            )

            response = agent.run("what is the current workspace?")

            self.assertEqual(response, "Workspace is available.")
            selection_context = json.loads(llm.messages[0][1]["content"])
            answer_context = json.loads(llm.messages[1][1]["content"])
            self.assertEqual(selection_context["workspace"]["path"], str(workspace))
            self.assertEqual(answer_context["workspace"]["path"], str(workspace))

    def test_plain_answer_prompt_mentions_web_search_for_current_information(self):
        llm = FakeLLM(
            [
                json.dumps(
                    {
                        "type": "skill_selection",
                        "selected_skill": None,
                        "confidence": 0.1,
                        "reason": "plain answer",
                    }
                ),
                "plain",
            ]
        )
        agent = SkillRuntimeAgent(
            llm,
            workspace_context={"available_tools": ["web_search"]},
        )

        agent.run("look up today's news")

        plain_prompt = llm.messages[1][0]["content"]
        self.assertIn("web_search", plain_prompt)
        self.assertIn("current", plain_prompt.lower())

    def test_stream_selected_skill_yields_llm_chunks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "code-review",
                            "confidence": 0.9,
                            "reason": "selected",
                        }
                    ),
                    ["# Output", "\n\nDone"],
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)

            chunks = list(agent.stream("review this project"))

            self.assertEqual(chunks, ["# Output", "\n\nDone"])
            self.assertEqual(len(llm.stream_messages), 1)

    def test_runtime_saves_final_response_to_session_memory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            skills_dir = root / "skills"
            memory_file = root / "session.json"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": None,
                            "confidence": 0.2,
                            "reason": "no skill",
                        }
                    ),
                    "Plain answer",
                ]
            )
            memory = SessionMemory(file_path=memory_file)
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir, session_memory=memory)
            runtime = YCAgentRuntime(agent)

            response = runtime.run("hello")

            saved_messages = json.loads(memory_file.read_text(encoding="utf-8"))
            self.assertEqual(response, "Plain answer")
            self.assertEqual(saved_messages[-1]["content"], "Plain answer")

    def test_run_includes_rag_results_when_selected_skill_allows_rag_search(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir, allowed_tools=["rag_search"])
            rag_tool = FakeRAGSearchTool()
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "code-review",
                            "confidence": 0.9,
                            "reason": "selected",
                        }
                    ),
                    "RAG-backed answer",
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                rag_search_tool=rag_tool,
            )

            response = agent.run("summarize architecture and risks")

            answer_context = llm.messages[1][1]["content"]
            self.assertEqual(response, "RAG-backed answer")
            self.assertEqual(
                rag_tool.calls,
                [{"query": "summarize architecture and risks", "top_k": 3}],
            )
            self.assertIn("rag_results", answer_context)
            self.assertIn("report-standard", answer_context)

    def test_runtime_handles_markdown_writer_tool_call_and_final_answer(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            skills_dir = root / "skills"
            output_dir = root / "outputs"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "code-review",
                            "confidence": 0.9,
                            "reason": "selected",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_call",
                            "tool_name": "markdown_writer",
                            "arguments": {
                                "file_name": "audit_note",
                                "content": "# Audit\n\nSaved.",
                            },
                            "reason": "save audit note",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "final_answer",
                            "content": "Audit note saved.",
                        }
                    ),
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)
            registry = ToolRegistry()
            registry.register(MarkdownWriterTool(output_dir=output_dir))
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["markdown_writer"],
            )

            response = runtime.run("save the review note")

            self.assertEqual(response, "Audit note saved.")
            self.assertTrue((output_dir / "audit_note.md").exists())
            self.assertEqual(len(llm.messages), 3)
            self.assertIn("tool_result", llm.messages[2][1]["content"])

    def test_observation_prompt_allows_follow_up_tool_call_or_final_answer(self):
        llm = FakeLLM(
            [
                json.dumps(
                    {
                        "type": "final_answer",
                        "content": "done",
                    }
                )
            ]
        )
        agent = SkillRuntimeAgent(llm)

        agent.run_with_observation(
            "review this project",
            {
                "tool_call": {
                    "type": "tool_call",
                    "tool_name": "workspace_files",
                    "arguments": {},
                },
                "tool_result": {"files": [{"path": "app.py"}]},
            },
        )

        system_prompt = llm.messages[0][0]["content"]
        self.assertIn("tool_call", system_prompt)
        self.assertIn("final_answer", system_prompt)
        self.assertIn("If another tool is needed", system_prompt)
        self.assertNotIn("Return only valid final_answer JSON", system_prompt)

    def test_run_retries_when_skill_execution_repeats_skill_selection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "code-review",
                            "confidence": 0.95,
                            "reason": "selected",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "code-review",
                            "confidence": 0.95,
                            "reason": "repeated by mistake",
                        }
                    ),
                    "Please share the project review scope.",
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)

            response = agent.run("review this project")

            self.assertEqual(response, "Please share the project review scope.")
            self.assertEqual(len(llm.messages), 3)
            self.assertIn("skill_selection", llm.messages[2][0]["content"])

    def test_runtime_agent_includes_project_instructions_in_plain_answer_prompt(self):
        llm = FakeLLM(
            [
                json.dumps(
                    {
                        "type": "skill_selection",
                        "selected_skill": None,
                        "confidence": 0.1,
                        "reason": "plain answer",
                    }
                ),
                "plain",
            ]
        )
        prompt_builder = PromptBuilder(
            [
                ProjectInstruction("YCORE.md", None, "Root project rule"),
                ProjectInstruction(".ycore/YCORE.md", None, "Local project rule"),
            ]
        )
        agent = SkillRuntimeAgent(llm, prompt_builder=prompt_builder)

        agent.run("hello")

        plain_prompt = llm.messages[1][0]["content"]
        self.assertIn("Root project rule", plain_prompt)
        self.assertIn("Local project rule", plain_prompt)
        self.assertLess(
            plain_prompt.index("Root project rule"),
            plain_prompt.index("Local project rule"),
        )

    def test_runtime_agent_core_prompt_is_not_word_or_paper_specific(self):
        llm = FakeLLM(
            [
                json.dumps(
                    {
                        "type": "skill_selection",
                        "selected_skill": None,
                        "confidence": 0.1,
                        "reason": "plain answer",
                    }
                ),
                "plain",
            ]
        )
        agent = SkillRuntimeAgent(llm)

        agent.run("hello")

        plain_prompt = llm.messages[1][0]["content"]
        self.assertNotIn("docx_format_normalizer", plain_prompt)
        self.assertNotIn("Word document automation", plain_prompt)
        self.assertNotIn("论文", plain_prompt)


if __name__ == "__main__":
    unittest.main()
