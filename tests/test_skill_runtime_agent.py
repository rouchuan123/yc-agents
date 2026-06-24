import json
import tempfile
import unittest
from pathlib import Path

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.session import SessionMemory
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


def write_skill(skills_dir, allowed_tools=None):
    allowed_tools = allowed_tools or ["markdown_writer"]
    skill_dir = skills_dir / "document-format-normalizer"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    lines = [
        "---",
        "name: document-format-normalizer",
        "description: Use when the user wants to normalize Word document format.",
        "allowed_tools:",
    ]
    lines.extend(f"  - {tool}" for tool in allowed_tools)
    lines.extend(
        [
            "---",
            "",
            "# Word 文档格式调整 Skill",
            "",
            "请根据用户提供的 .docx 路径调用工具并说明输出文件。",
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
                    "可以读取当前工作区。",
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

            response = agent.run("当前工作区是什么？")

            self.assertEqual(response, "可以读取当前工作区。")
            selection_context = json.loads(llm.messages[0][1]["content"])
            answer_context = json.loads(llm.messages[1][1]["content"])
            self.assertEqual(selection_context["workspace"]["path"], str(workspace))
            self.assertEqual(answer_context["workspace"]["path"], str(workspace))

    def test_stream_selected_skill_yields_llm_chunks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "document-format-normalizer",
                            "confidence": 0.9,
                            "reason": "selected",
                        }
                    ),
                    ["# 输出", "\n\n已处理"],
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)

            chunks = list(agent.stream("调整 draft.docx"))

            self.assertEqual(chunks, ["# 输出", "\n\n已处理"])
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
                    "普通回答",
                ]
            )
            memory = SessionMemory(file_path=memory_file)
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir, session_memory=memory)
            runtime = YCAgentRuntime(agent)

            response = runtime.run("你好")

            saved_messages = json.loads(memory_file.read_text(encoding="utf-8"))
            self.assertEqual(response, "普通回答")
            self.assertEqual(saved_messages[-1]["content"], "普通回答")

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
                            "selected_skill": "document-format-normalizer",
                            "confidence": 0.9,
                            "reason": "selected",
                        }
                    ),
                    "基于 RAG 的回答",
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                rag_search_tool=rag_tool,
            )

            response = agent.run("按 report-standard 调整格式")

            answer_context = llm.messages[1][1]["content"]
            self.assertEqual(response, "基于 RAG 的回答")
            self.assertEqual(
                rag_tool.calls,
                [{"query": "按 report-standard 调整格式", "top_k": 3}],
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
                            "selected_skill": "document-format-normalizer",
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

            response = runtime.run("保存审计说明")

            self.assertEqual(response, "Audit note saved.")
            self.assertTrue((output_dir / "audit_note.md").exists())
            self.assertEqual(len(llm.messages), 3)
            self.assertIn("tool_result", llm.messages[2][1]["content"])

    def test_run_retries_when_skill_execution_repeats_skill_selection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "document-format-normalizer",
                            "confidence": 0.95,
                            "reason": "selected",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "document-format-normalizer",
                            "confidence": 0.95,
                            "reason": "repeated by mistake",
                        }
                    ),
                    "请提供 draft.docx 路径。",
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)

            response = agent.run("帮我调整 Word 格式")

            self.assertEqual(response, "请提供 draft.docx 路径。")
            self.assertEqual(len(llm.messages), 3)
            self.assertIn("skill_selection", llm.messages[2][0]["content"])


if __name__ == "__main__":
    unittest.main()
