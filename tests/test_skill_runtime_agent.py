import json
import tempfile
import unittest
from pathlib import Path

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.harness.json_protocol import InvalidModelJSONError
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.session import SessionMemory
from yc_agents.prompts.builder import PromptBuilder
from yc_agents.prompts.project_instructions import ProjectInstruction
from yc_agents.skills.definition import SkillDefinition
from yc_agents.tools.base import BaseTool
from yc_agents.tools.file_reader import FileReaderTool
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.registry import ToolRegistry
from yc_agents.tools.web_search import WebSearchTool
from yc_agents.tools.workspace_write import WorkspaceWriteTool


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


class FakeWebSearchProvider:
    name = "fake-search"

    def __init__(self):
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "ok": True,
            "tool": "web_search",
            "provider": self.name,
            "query": kwargs["query"],
            "answer": "Found open source Git tools.",
            "results": [],
        }


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


class SkipAwareIntentRouter(FakeIntentRouter):
    def __init__(self):
        super().__init__()
        self.skip_flags = []

    def route(self, user_input, skills, allow_llm_skip=False):
        self.skip_flags.append(allow_llm_skip)
        return super().route(user_input, skills)


class CountingSessionMemory(SessionMemory):
    def __init__(self, file_path):
        super().__init__(file_path=file_path)
        self.load_calls = 0

    def load(self):
        self.load_calls += 1
        return super().load()


class CountingLongTermMemory:
    def __init__(self):
        self.search_calls = []

    def search(self, query, top_k=6, token_budget=4_000, exclude_session_id=None):
        self.search_calls.append(query)
        return [{"source": "session-1", "text": "past note"}]


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

    def test_runtime_never_returns_raw_skill_selection_text_as_final_answer(self):
        llm = FakeLLM(
            [
                "I can review code, read files, and run safe checks.",
                "still not valid selection JSON",
                json.dumps(
                    {
                        "type": "final_answer",
                        "content": "我可以进行代码审查、读取文件并运行安全检查。",
                    }
                ),
            ]
        )
        agent = SkillRuntimeAgent(llm)
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            fail_on_invalid_json=True,
        )

        response = runtime.run("what skills do you have?")

        self.assertEqual(response, "我可以进行代码审查、读取文件并运行安全检查。")
        self.assertEqual(len(llm.messages), 3)

    def test_invalid_skill_selection_repairs_once_then_runs_selected_skill(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    "我觉得应该用 code-review 来处理",
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "code-review",
                            "confidence": 0.9,
                            "reason": "repaired",
                        }
                    ),
                    json.dumps({"type": "final_answer", "content": "审查完成"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
            )

            response = agent.run("review this project")

            self.assertEqual(json.loads(response)["content"], "审查完成")
            self.assertEqual(len(llm.messages), 3)
            repair_prompt = llm.messages[1][0]["content"]
            self.assertIn("JSON protocol repairer", repair_prompt)
            self.assertIn("skill_selection", repair_prompt)

    def test_skill_selection_repair_failure_falls_back_to_plain_answer(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            llm = FakeLLM(
                [
                    "plain text instead of selection JSON",
                    "still not JSON",
                    json.dumps({"type": "final_answer", "content": "直接回答"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=Path(tmp_dir) / "skills",
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
            )

            response = agent.run("hello")

            self.assertEqual(json.loads(response)["content"], "直接回答")
            self.assertNotIn("plain text instead of selection JSON", response)
            self.assertEqual(len(llm.messages), 3)

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

    def test_selected_skill_does_not_trigger_rag_search_automatically(self):
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
            self.assertEqual(rag_tool.calls, [])
            self.assertIn("rag_results", answer_context)
            self.assertNotIn("report-standard", answer_context)

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
            # 工具结果通过追加的观察增量消息（列表末尾）送达模型。
            self.assertIn("tool_result", llm.messages[2][-1]["content"])

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
                "我将使用 code-review 进行处理。",
            )
            self.assertEqual(
                assistant_message["process_entries"][1]["content"],
                "我先保存一份分析笔记。",
            )
            self.assertEqual(
                assistant_message["process_entries"][2]["tool_name"],
                "markdown_writer",
            )
            self.assertEqual(assistant_message["process_entries"][3]["type"], "tool_result")

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

    def test_observation_execution_context_is_compact_without_skill_body(self):
        llm = FakeLLM([json.dumps({"type": "final_answer", "content": "done"})])
        agent = SkillRuntimeAgent(
            llm,
            workspace_context={"available_tools": ["workspace_files", "file_reader"]},
        )
        agent._set_skill_tool_context(
            SkillDefinition(
                name="code-review",
                description="Review a local project.",
                allowed_tools=["workspace_files", "file_reader"],
                body="Read the project, trace a critical path, then report evidence.",
            )
        )

        agent.run_with_observation(
            "review this project",
            {
                "tool_call": {"tool_name": "workspace_files", "arguments": {}},
                "tool_result": {"files": [{"path": "README.md"}]},
                "execution_history": [],
            },
        )

        payload = json.loads(llm.messages[0][1]["content"])
        selected_skill = payload["execution_context"]["selected_skill"]
        self.assertEqual(selected_skill["name"], "code-review")
        self.assertEqual(
            selected_skill["allowed_tools"],
            ["workspace_files", "file_reader"],
        )
        self.assertNotIn("body", selected_skill)
        self.assertIn("first execution message", selected_skill["stage_hint"])
        self.assertNotIn("trace a critical path", llm.messages[0][1]["content"])
        self.assertEqual(
            payload["execution_context"]["available_tools"],
            ["workspace_files", "file_reader"],
        )

    def test_skill_body_appears_only_in_first_execution_message(self):
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
                    json.dumps({"type": "final_answer", "content": "started"}),
                    json.dumps({"type": "final_answer", "content": "finished"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
            )

            agent.run("review this project")
            agent.run_with_observation(
                "review this project",
                {
                    "tool_call": {"tool_name": "workspace_files", "arguments": {}},
                    "tool_result": {"files": [{"path": "app.py"}]},
                    "execution_history": [],
                },
            )

            body_line = "Summarize the project structure, architecture, risks, and test gaps."
            self.assertIn(body_line, llm.messages[1][1]["content"])
            # 追加式轮消息：观察步只在冻结前缀之后追加增量，技能正文在
            # 整轮消息里出现且仅出现一次，绝不在增量消息中重发。
            observation_call = llm.messages[2]
            serialized = json.dumps(observation_call, ensure_ascii=False)
            self.assertEqual(serialized.count(body_line), 1)
            self.assertNotIn(body_line, observation_call[-1]["content"])

    def test_protocol_repair_messages_do_not_carry_skill_body(self):
        llm = FakeLLM([json.dumps({"type": "final_answer", "content": "repaired"})])
        agent = SkillRuntimeAgent(llm)
        agent._set_skill_tool_context(
            SkillDefinition(
                name="code-review",
                description="Review a local project.",
                allowed_tools=["workspace_files"],
                body="FULL SKILL BODY TEXT",
            )
        )

        agent.run_with_protocol_error(
            "review this project",
            InvalidModelJSONError("Model output is not valid JSON", raw_text="oops"),
            expectation={"allowed_types": ["final_answer"]},
        )

        user_payload = llm.messages[0][1]["content"]
        self.assertNotIn("FULL SKILL BODY TEXT", user_payload)
        payload = json.loads(user_payload)
        self.assertEqual(payload["execution_context"]["selected_skill"], "code-review")

    def test_verification_revision_keeps_compact_skill_context_and_execution_history(self):
        llm = FakeLLM([json.dumps({"type": "final_answer", "content": "revised"})])
        agent = SkillRuntimeAgent(
            llm,
            workspace_context={"available_tools": ["workspace_files", "file_reader"]},
        )
        agent._set_skill_tool_context(
            SkillDefinition(
                name="code-review",
                description="Review a local project.",
                allowed_tools=["workspace_files", "file_reader"],
                body="Read evidence and report findings by severity.",
            )
        )
        history = [
            {
                "tool_call": {"tool_name": "workspace_files", "arguments": {}},
                "tool_result": {"ok": True, "files": ["README.md"]},
            }
        ]

        response = agent.run_with_verification_feedback(
            "review this project",
            "",
            {"passed": False, "checks": [{"message": "Final output is empty"}]},
            execution_history=history,
        )

        payload = json.loads(llm.messages[0][1]["content"])
        self.assertEqual(json.loads(response)["content"], "revised")
        self.assertEqual(payload["execution_context"]["selected_skill"]["name"], "code-review")
        self.assertNotIn("body", payload["execution_context"]["selected_skill"])
        self.assertNotIn("Read evidence and report findings by severity.", llm.messages[0][1]["content"])
        self.assertEqual(payload["execution_context"]["available_tools"], ["workspace_files", "file_reader"])
        self.assertEqual(payload["execution_history"], history)

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

    def test_memory_context_is_loaded_once_per_turn_and_reused_by_observations(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = CountingSessionMemory(Path(tmp_dir) / "session.json")
            long_term = CountingLongTermMemory()
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
                    json.dumps({"type": "final_answer", "content": "plain"}),
                    json.dumps({"type": "final_answer", "content": "after obs 1"}),
                    json.dumps({"type": "final_answer", "content": "after obs 2"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=Path(tmp_dir) / "skills",
                session_memory=memory,
                long_term_memory=long_term,
            )
            observation = {
                "tool_call": {"tool_name": "workspace_files", "arguments": {}},
                "tool_result": {"files": []},
                "execution_history": [],
            }

            agent.run("分析项目")
            agent.run_with_observation("分析项目", observation)
            agent.run_with_observation("分析项目", observation)

            self.assertEqual(memory.load_calls, 1)
            self.assertEqual(long_term.search_calls, ["分析项目"])
            observation_payload = json.loads(llm.messages[2][1]["content"])
            self.assertEqual(
                observation_payload["memory"]["retrieved"],
                [{"source": "session-1", "text": "past note"}],
            )

    def test_remember_turn_invalidates_turn_memory_cache(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = CountingSessionMemory(Path(tmp_dir) / "session.json")
            long_term = CountingLongTermMemory()
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
                    json.dumps({"type": "final_answer", "content": "plain"}),
                    json.dumps({"type": "final_answer", "content": "after turn"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=Path(tmp_dir) / "skills",
                session_memory=memory,
                long_term_memory=long_term,
            )
            observation = {
                "tool_call": {"tool_name": "workspace_files", "arguments": {}},
                "tool_result": {"files": []},
                "execution_history": [],
            }

            agent.run("分析项目")
            agent.remember_turn("分析项目", "回答")
            agent.run_with_observation("分析项目", observation)

            self.assertEqual(long_term.search_calls, ["分析项目", "分析项目"])

    def test_next_turn_continuation_reuses_previous_skill_without_reselection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            write_skill(skills_dir, name="eval-writer", allowed_tools=[])
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
                    json.dumps({"type": "final_answer", "content": "第一轮完成"}),
                    json.dumps({"type": "final_answer", "content": "继续完成"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
            )

            agent.run("review this project")
            response = agent.run("继续下一步")

            self.assertEqual(json.loads(response)["content"], "继续完成")
            self.assertEqual(len(llm.messages), 3)
            second_turn_payload = json.loads(llm.messages[2][1]["content"])
            self.assertEqual(second_turn_payload["task"], "skill_execution")
            self.assertEqual(second_turn_payload["selected_skill"]["name"], "code-review")
            self.assertTrue(second_turn_payload["selection"].get("sticky"))

    def test_continuation_mentioning_other_skill_reselects(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            write_skill(skills_dir, name="eval-writer", allowed_tools=[])
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
                    json.dumps({"type": "final_answer", "content": "第一轮完成"}),
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "eval-writer",
                            "confidence": 0.9,
                            "reason": "switch",
                        }
                    ),
                    json.dumps({"type": "final_answer", "content": "评估完成"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
            )

            agent.run("review this project")
            response = agent.run("接下来用 eval-writer 帮我写评估")

            self.assertEqual(json.loads(response)["content"], "评估完成")
            self.assertEqual(len(llm.messages), 4)
            second_selection_payload = json.loads(llm.messages[2][1]["content"])
            self.assertEqual(second_selection_payload["task"], "skill_selection")

    def test_plain_turn_does_not_stick_to_any_skill(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
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
                    json.dumps({"type": "final_answer", "content": "第一轮"}),
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": None,
                            "confidence": 0.1,
                            "reason": "plain again",
                        }
                    ),
                    json.dumps({"type": "final_answer", "content": "第二轮"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
            )

            agent.run("hello")
            agent.run("继续")

            self.assertEqual(len(llm.messages), 4)
            second_selection_payload = json.loads(llm.messages[2][1]["content"])
            self.assertEqual(second_selection_payload["task"], "skill_selection")

    def test_agent_enables_llm_skip_when_router_supports_it(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir, name="eval-writer", allowed_tools=[])
            router = SkipAwareIntentRouter()
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
                    json.dumps({"type": "final_answer", "content": "评估方案"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                session_memory=SessionMemory(file_path=Path(tmp_dir) / "session.json"),
                intent_router=router,
            )

            agent.run("帮我写 eval")

            self.assertEqual(router.skip_flags, [True])

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


    def test_selected_skill_can_use_any_globally_enabled_tool(self):
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
                            "reason": "save review",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "final_answer",
                            "content": "saved",
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

            response = runtime.run("review this project")

            self.assertEqual(response, "saved")
            self.assertTrue((root / "outputs" / "blocked.md").exists())

    def test_plain_answer_can_use_any_globally_enabled_tool(self):
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
                    json.dumps(
                        {
                            "type": "final_answer",
                            "content": "saved",
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

            response = runtime.run("hello")

            self.assertEqual(response, "saved")
            self.assertTrue((root / "outputs" / "plain.md").exists())

    def test_plain_answer_allows_globally_enabled_web_search(self):
        llm = FakeLLM(
            [
                json.dumps(
                    {
                        "type": "skill_selection",
                        "selected_skill": None,
                        "confidence": 0.1,
                        "reason": "plain web search",
                    }
                ),
                json.dumps(
                    {
                        "type": "tool_call",
                        "tool_name": "web_search",
                        "arguments": {
                            "query": "open source Git tools",
                            "max_results": 5,
                        },
                        "reason": "search current web information",
                    }
                ),
                json.dumps(
                    {
                        "type": "final_answer",
                        "content": "Found open source Git tools.",
                    }
                ),
            ]
        )
        provider = FakeWebSearchProvider()
        registry = ToolRegistry()
        registry.register(WebSearchTool(provider=provider))
        agent = SkillRuntimeAgent(llm)
        runtime = YCAgentRuntime(
            agent,
            expects_json=True,
            tool_registry=registry,
            allowed_tools=["web_search"],
        )

        response = runtime.run("帮我搜搜有什么开源的 Git 工具")

        self.assertEqual(response, "Found open source Git tools.")
        self.assertEqual(provider.calls[0]["query"], "open source Git tools")

    def test_selected_skill_can_use_globally_enabled_workspace_write(self):
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
                            "reason": "edit requested",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_call",
                            "tool_name": "workspace_write",
                            "arguments": {
                                "file_path": "notes.txt",
                                "operation": "create",
                                "content": "created by agent\n",
                            },
                            "reason": "create requested workspace file",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "final_answer",
                            "content": "Created notes.txt.",
                        }
                    ),
                ]
            )
            registry = ToolRegistry()
            registry.register(WorkspaceWriteTool(root))
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                workspace_context={"available_tools": ["workspace_write"]},
            )
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=registry,
                allowed_tools=["workspace_write"],
            )

            response = runtime.run("Create notes.txt in the workspace")

            self.assertEqual(response, "Created notes.txt.")
            self.assertEqual(
                (root / "notes.txt").read_text(encoding="utf-8"),
                "created by agent\n",
            )

    def test_runtime_ignores_legacy_unknown_tool_declared_by_skill(self):
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
                if event["event_type"] == "enabled_tool_missing"
            ]
            self.assertEqual(missing_events, [])

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
            observation_payload = json.loads(llm.messages[2][-1]["content"])
            self.assertIn("def handler", observation_payload["observation"]["tool_result"]["text"])

    def test_memory_prompt_strips_process_entries_but_file_keeps_them(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory_file = Path(tmp_dir) / "session.json"
            seeded = SessionMemory(file_path=memory_file)
            seeded.add_message("user", "分析项目")
            seeded.add_structured_message(
                "assistant",
                "最终分析",
                process_entries=[
                    {
                        "type": "tool_result",
                        "tool_name": "workspace_files",
                        "summary": "找到 7 个文件。",
                    }
                ],
            )
            seeded.save()
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
                    json.dumps({"type": "final_answer", "content": "好的"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=Path(tmp_dir) / "skills",
                session_memory=SessionMemory(file_path=memory_file),
            )

            agent.run("hello")

            payload = json.loads(llm.messages[-1][-1]["content"])
            session_messages = payload["memory"]["session"]
            self.assertEqual(
                session_messages[-1],
                {"role": "assistant", "content": "最终分析"},
            )
            for message in session_messages:
                self.assertNotIn("process_entries", message)
            saved = json.loads(memory_file.read_text(encoding="utf-8"))
            self.assertIn("process_entries", saved[-1])

    def test_compaction_persists_process_entries_while_prompt_stays_clean(self):
        from yc_agents.memory.compressor import MemoryCompressor
        from yc_agents.memory.summary import SummaryMemory

        with tempfile.TemporaryDirectory() as tmp_dir:
            memory_file = Path(tmp_dir) / "session.json"
            seeded = SessionMemory(file_path=memory_file)
            for index in range(3):
                seeded.add_message("user", f"问题{index}:" + "x" * 200)
                seeded.add_structured_message(
                    "assistant",
                    f"回答{index}:" + "x" * 200,
                    process_entries=[{"type": "assistant_step", "content": "看文件"}],
                )
            seeded.save()
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
                    json.dumps({"type": "final_answer", "content": "好的"}),
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=Path(tmp_dir) / "skills",
                session_memory=SessionMemory(file_path=memory_file),
                memory_compressor=MemoryCompressor(
                    summary_memory=SummaryMemory(Path(tmp_dir) / "summary.md")
                ),
                memory_config={"activeContextMaxTokens": 1},
            )

            agent.run("hello")

            saved = json.loads(memory_file.read_text(encoding="utf-8"))
            self.assertLess(len(saved), 6)
            self.assertTrue(any("process_entries" in message for message in saved))
            payload = json.loads(llm.messages[-1][-1]["content"])
            for message in payload["memory"]["session"]:
                self.assertNotIn("process_entries", message)


if __name__ == "__main__":
    unittest.main()
