import json
import tempfile
import unittest
from pathlib import Path

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.session import SessionMemory
from yc_agents.prompts.builder import PromptBuilder
from yc_agents.prompts.project_instructions import ProjectInstruction
from yc_agents.tools.base import BaseTool
from yc_agents.tools.file_reader import FileReaderTool
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


class FencedSelectionThenFinalLLM:
    def __init__(self):
        self.calls = []

    def think_json(self, messages, **kwargs):
        self.calls.append(("think_json", messages))
        if len(self.calls) == 1:
            return (
                "```json\n"
                '{"type":"skill_selection","selected_skill":null,"confidence":0.1,"reason":"simple question"}'
                "\n```"
            )
        return '{"type":"final_answer","content":"I am YCore."}'

    def think(self, messages, **kwargs):
        self.calls.append(("think", messages))
        return '{"type":"final_answer","content":"fallback"}'


class MiMoShapedLLM:
    def __init__(self):
        self.calls = 0

    def think_json(self, messages, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return (
                "```json\n"
                '{"type":"skill_selection","selected_skill":null,"confidence":0.1,"reason":"simple identity question"}'
                "\n```"
            )
        return '{"type":"final_answer","content":"I am YCore running on the configured model provider."}'

    def think(self, messages, **kwargs):
        return self.think_json(messages, **kwargs)


class FakeRAGSearchTool:
    def __init__(self):
        self.calls = []

    def run(self, query, top_k=3):
        self.calls.append({"query": query, "top_k": top_k})
        return [{"source": "template.md", "text": "report-standard"}]


class WorkspaceFilesStubTool(BaseTool):
    name = "workspace_files"
    description = "Stub workspace listing tool."

    def run(self, pattern="*"):
        return {"files": [{"path": "app.py"}]}


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


class FakeIntentRouter:
    def __init__(self):
        self.calls = []

    def route(self, user_input, skills):
        self.calls.append((user_input, skills))
        return {
            "type": "intent_route",
            "selected_skill": skills[0].name,
            "confidence": 0.9,
            "candidates": [
                {
                    "skill_name": skills[0].name,
                    "score": 0.9,
                    "components": {"rule": 1.0, "semantic": 0.5, "llm": 0.8},
                    "reasons": {"rule": "trigger matched"},
                }
            ],
        }


class TestSkillRuntimeAgent(unittest.TestCase):
    def test_runtime_agent_accepts_fenced_skill_selection_and_answers_with_final_answer_json(self):
        agent = SkillRuntimeAgent(
            FencedSelectionThenFinalLLM(),
            session_memory=SessionMemory(),
        )

        response = agent.run("what model are you")

        self.assertEqual(json.loads(response)["type"], "final_answer")
        self.assertEqual(json.loads(response)["content"], "I am YCore.")

    def test_runtime_agent_prefers_think_json_for_protocol_turns(self):
        llm = FencedSelectionThenFinalLLM()
        agent = SkillRuntimeAgent(llm, session_memory=SessionMemory())

        agent.run("what model are you")

        self.assertEqual([call[0] for call in llm.calls], ["think_json", "think_json"])

    def test_mimo_shaped_fenced_skill_selection_regression_returns_final_answer_json(self):
        agent = SkillRuntimeAgent(MiMoShapedLLM(), session_memory=SessionMemory())

        response = agent.run("what model are you")

        data = json.loads(response)
        self.assertEqual(data["type"], "final_answer")
        self.assertEqual(
            data["content"],
            "I am YCore running on the configured model provider.",
        )

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

    def test_runtime_treats_plain_skill_selection_output_as_final_answer(self):
        llm = FakeLLM(["I can review code, read files, and run safe checks."])
        agent = SkillRuntimeAgent(llm)
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            fail_on_invalid_json=True,
        )

        response = runtime.run("what skills do you have?")

        self.assertEqual(response, "I can review code, read files, and run safe checks.")
        self.assertEqual(len(llm.messages), 1)

    def test_runtime_agent_saves_structured_process_entries_to_session_memory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory_file = Path(tmp_dir) / "session.json"
            memory = SessionMemory(file_path=memory_file)
            agent = SkillRuntimeAgent(FakeLLM([]), session_memory=memory)

            agent.remember_structured_turn(
                "分析项目",
                "最终分析",
                [
                    {"type": "assistant_step", "content": "我先看文件。"},
                    {
                        "type": "tool_result",
                        "tool_name": "workspace_files",
                        "summary": "找到 7 个文件。",
                    },
                ],
            )

            saved = json.loads(memory_file.read_text(encoding="utf-8"))
            self.assertEqual(saved[-2], {"role": "user", "content": "分析项目"})
            self.assertEqual(saved[-1]["role"], "assistant")
            self.assertEqual(saved[-1]["content"], "最终分析")
            self.assertEqual(saved[-1]["process_entries"][0]["content"], "我先看文件。")

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

    def test_project_analysis_flow_saves_process_entries_and_final_answer(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            skills_dir = root / "skills"
            memory_file = root / "session.json"
            output_dir = root / "outputs"
            write_skill(skills_dir, allowed_tools=["markdown_writer"])
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
                            "message": "我先保存一份分析笔记。",
                            "tool_name": "markdown_writer",
                            "arguments": {
                                "file_name": "analysis",
                                "content": "# Analysis",
                            },
                            "reason": "save note",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "final_answer",
                            "content": "项目分析完成。",
                        }
                    ),
                ]
            )
            memory = SessionMemory(file_path=memory_file)
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir, session_memory=memory)
            registry = ToolRegistry()
            registry.register(MarkdownWriterTool(output_dir=output_dir))
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["markdown_writer"],
            )

            response = runtime.run("分析项目")

            saved = json.loads(memory_file.read_text(encoding="utf-8"))
            assistant_message = saved[-1]
            self.assertEqual(response, "项目分析完成。")
            self.assertEqual(assistant_message["content"], "项目分析完成。")
            self.assertEqual(
                assistant_message["process_entries"][0]["content"],
                "我先保存一份分析笔记。",
            )
            self.assertEqual(
                assistant_message["process_entries"][1]["tool_name"],
                "markdown_writer",
            )
            self.assertEqual(assistant_message["process_entries"][2]["type"], "tool_result")

    def test_observation_prompt_requires_follow_up_tool_call_or_final_answer_json(self):
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
        self.assertIn("return final_answer JSON", system_prompt)
        self.assertIn("Do not wrap final answers in Markdown fences", system_prompt)
        self.assertNotIn("answer directly in natural language", system_prompt)
        self.assertNotIn("Do not wrap final answers in JSON", system_prompt)
        self.assertIn("If another tool is needed", system_prompt)

    def test_tool_protocol_tells_model_to_put_progress_in_message_field(self):
        builder = PromptBuilder()
        prompt = builder.plain_answer_messages(
            user_input="分析项目",
            memory={"session": []},
            workspace_context={"available_tools": ["workspace_files"]},
        )[0]["content"]

        self.assertIn('"message"', prompt)
        self.assertIn("visible progress", prompt)
        self.assertIn("return only valid tool_call JSON", prompt)

    def test_observation_protocol_allows_progress_message_on_follow_up_tool_call(self):
        builder = PromptBuilder()
        prompt = builder.observation_messages(
            user_input="分析项目",
            memory={"session": []},
            workspace_context={"available_tools": ["workspace_files"]},
            observation={"tool_result": {"files": []}},
        )[0]["content"]

        self.assertIn('"message"', prompt)
        self.assertIn("visible progress", prompt)
        self.assertIn("return final_answer JSON", prompt)
        self.assertNotIn("answer directly in natural language", prompt)

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

    def test_runtime_agent_core_prompt_is_not_word_or_old_domain_specific(self):
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
        self.assertNotIn("docx" + "_format" + "_normalizer", plain_prompt)
        self.assertNotIn("Word document automation", plain_prompt)
        self.assertNotIn("论文", plain_prompt)

    def test_skill_runtime_agent_uses_intent_router_for_candidate_order(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            skills_dir.mkdir()
            write_skill(skills_dir, name="eval-writer", allowed_tools=[])
            router = FakeIntentRouter()
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "eval-writer",
                            "confidence": 0.9,
                            "reason": "route",
                        }
                    ),
                    "评估方案",
                ]
            )

            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir, intent_router=router)

            self.assertEqual(agent.run("帮我写 eval"), "评估方案")
            self.assertTrue(router.calls)


    def test_runtime_denies_global_tool_not_allowed_by_selected_skill(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            skills_dir = root / "skills"
            write_skill(skills_dir, allowed_tools=["workspace_files"])
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
                                "file_name": "blocked",
                                "content": "blocked",
                            },
                            "reason": "should be denied",
                        }
                    ),
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)
            registry = ToolRegistry()
            registry.register(MarkdownWriterTool(output_dir=root / "outputs"))
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["workspace_files", "markdown_writer"],
            )

            with self.assertRaises(Exception) as caught:
                runtime.run("review this project")

            self.assertIn("Tool is not allowed: markdown_writer", str(caught.exception))

    def test_plain_answer_only_allows_minimal_workspace_tools(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": None,
                            "confidence": 0.1,
                            "reason": "plain",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_call",
                            "tool_name": "markdown_writer",
                            "arguments": {
                                "file_name": "plain",
                                "content": "plain",
                            },
                            "reason": "should be denied in plain answer",
                        }
                    ),
                ]
            )
            agent = SkillRuntimeAgent(llm)
            registry = ToolRegistry()
            registry.register(MarkdownWriterTool(output_dir=root / "outputs"))
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["workspace_files", "file_reader", "markdown_writer"],
            )

            with self.assertRaises(Exception) as caught:
                runtime.run("hello")

            self.assertIn("Tool is not allowed: markdown_writer", str(caught.exception))

    def test_runtime_records_unknown_tool_declared_by_skill_without_failing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            skills_dir = root / "skills"
            write_skill(skills_dir, allowed_tools=["workspace_files", "ghost_tool"])
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
                            "tool_name": "workspace_files",
                            "arguments": {},
                            "reason": "list files",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "final_answer",
                            "content": "done",
                        }
                    ),
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)
            registry = ToolRegistry()
            registry.register(WorkspaceFilesStubTool())
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["workspace_files"],
            )

            response = runtime.run("review this project")

            self.assertEqual(response, "done")
            missing_events = [
                event for event in runtime.last_trace_events
                if event["event_type"] == "skill_allowed_tool_missing"
            ]
            self.assertEqual(len(missing_events), 1)
            self.assertEqual(missing_events[0]["payload"]["tool_name"], "ghost_tool")

    def test_runtime_can_read_python_file_through_file_reader_tool_call(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "app.py").write_text("def handler():\n    return 'ok'\n", encoding="utf-8")
            skills_dir = root / "skills"
            write_skill(skills_dir, allowed_tools=["file_reader"])
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
                            "tool_name": "file_reader",
                            "arguments": {"file_path": "app.py"},
                            "reason": "read python source",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "final_answer",
                            "content": "read app.py",
                        }
                    ),
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)
            registry = ToolRegistry()
            registry.register(FileReaderTool(workspace))
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["file_reader"],
            )

            response = runtime.run("review python file")

            self.assertEqual(response, "read app.py")
            observation_payload = json.loads(llm.messages[2][1]["content"])
            self.assertIn("def handler", observation_payload["observation"]["tool_result"]["text"])


if __name__ == "__main__":
    unittest.main()
