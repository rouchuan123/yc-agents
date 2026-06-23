import tempfile
import unittest
import json
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

    def think(self, messages):
        self.messages.append(messages)
        return self.responses.pop(0)


class FakeSummaryMemory:
    def load(self):
        return "阶段摘要：已经接入 SessionMemory。"


class FakeProfileMemory:
    def load(self):
        return {
            "major": "通信工程",
            "research_direction": "工业遮挡失联场景定位",
        }


class FakeMemoryCompressor:
    def __init__(self):
        self.received_messages = None

    def compress_and_save(self, messages):
        self.received_messages = messages
        return "自动压缩后的阶段摘要"


class FakeRAGSearchTool:
    def __init__(self):
        self.calls = []

    def run(self, query, top_k=3):
        self.calls.append({"query": query, "top_k": top_k})
        return [
            {
                "source": "paper.md",
                "chunk_id": 0,
                "score": 2,
                "text": "工业遮挡会影响定位稳定性。",
            }
        ]


def write_skill(skills_dir):
    skill_dir = skills_dir / "opening-report"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "\n".join(
            [
                "---",
                "name: opening-report",
                "description: Use when the user wants help with opening reports.",
                "allowed_tools:",
                "  - markdown_writer",
                "---",
                "",
                "# 开题报告 Skill",
                "",
                "请先确认研究方向，再给出下一步建议。",
            ]
        ),
        encoding="utf-8",
    )


class TestSkillRuntimeAgent(unittest.TestCase):
    def test_runtime_saves_final_response_to_session_memory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            skills_dir = tmp_path / "skills"
            memory_file = tmp_path / "session.json"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    (
                        '{"type":"skill_selection",'
                        '"selected_skill":null,'
                        '"confidence":0.2,'
                        '"reason":"没有合适 Skill"}'
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
            self.assertEqual(
                saved_messages,
                [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "普通回答"},
                ],
            )

    def test_run_includes_session_memory_in_model_context(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            skills_dir = tmp_path / "skills"
            memory_file = tmp_path / "session.json"
            write_skill(skills_dir)
            memory = SessionMemory(file_path=memory_file)
            memory.add_message("user", "上一轮问题")
            memory.add_message("assistant", "上一轮回答")
            memory.save()
            llm = FakeLLM(
                [
                    (
                        '{"type":"skill_selection",'
                        '"selected_skill":"opening-report",'
                        '"confidence":0.9,'
                        '"reason":"用户正在准备开题"}'
                    ),
                    "这是基于记忆的回答。",
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir, session_memory=memory)

            response = agent.run("继续")

            self.assertEqual(response, "这是基于记忆的回答。")
            selection_context = llm.messages[0][1]["content"]
            answer_context = llm.messages[1][1]["content"]
            self.assertIn("上一轮问题", selection_context)
            self.assertIn("上一轮回答", selection_context)
            self.assertIn("上一轮问题", answer_context)
            self.assertIn("上一轮回答", answer_context)

    def test_run_includes_summary_and_profile_memory_in_model_context(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            skills_dir = tmp_path / "skills"
            memory_file = tmp_path / "session.json"
            write_skill(skills_dir)
            memory = SessionMemory(file_path=memory_file)
            memory.add_message("user", "上一轮问题")
            memory.save()
            llm = FakeLLM(
                [
                    (
                        '{"type":"skill_selection",'
                        '"selected_skill":"opening-report",'
                        '"confidence":0.9,'
                        '"reason":"用户正在准备开题"}'
                    ),
                    "这是基于三层记忆的回答。",
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                session_memory=memory,
                summary_memory=FakeSummaryMemory(),
                profile_memory=FakeProfileMemory(),
            )

            response = agent.run("继续")

            self.assertEqual(response, "这是基于三层记忆的回答。")
            selection_context = llm.messages[0][1]["content"]
            answer_context = llm.messages[1][1]["content"]
            self.assertIn("阶段摘要：已经接入 SessionMemory。", selection_context)
            self.assertIn("通信工程", selection_context)
            self.assertIn("阶段摘要：已经接入 SessionMemory。", answer_context)
            self.assertIn("工业遮挡失联场景定位", answer_context)

    def test_run_triggers_memory_compression_when_threshold_reached(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            skills_dir = tmp_path / "skills"
            memory_file = tmp_path / "session.json"
            write_skill(skills_dir)
            memory = SessionMemory(file_path=memory_file)
            memory.add_message("user", "问题 1")
            memory.add_message("assistant", "回答 1")
            memory.add_message("user", "问题 2")
            memory.save()
            compressor = FakeMemoryCompressor()
            llm = FakeLLM(
                [
                    (
                        '{"type":"skill_selection",'
                        '"selected_skill":"opening-report",'
                        '"confidence":0.9,'
                        '"reason":"用户正在准备开题"}'
                    ),
                    "这是基于压缩摘要的回答。",
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                session_memory=memory,
                memory_compressor=compressor,
                compression_threshold=3,
            )

            response = agent.run("继续")

            selection_context = llm.messages[0][1]["content"]
            self.assertEqual(response, "这是基于压缩摘要的回答。")
            self.assertEqual(len(compressor.received_messages), 3)
            self.assertIn("自动压缩后的阶段摘要", selection_context)

    def test_run_includes_rag_results_when_selected_skill_allows_rag_search(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            skills_dir = tmp_path / "skills"
            skill_dir = skills_dir / "opening-report"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: opening-report",
                        "description: Use when the user wants help with opening reports.",
                        "allowed_tools:",
                        "  - rag_search",
                        "---",
                        "",
                        "# 开题报告 Skill",
                    ]
                ),
                encoding="utf-8",
            )
            rag_tool = FakeRAGSearchTool()
            llm = FakeLLM(
                [
                    (
                        '{"type":"skill_selection",'
                        '"selected_skill":"opening-report",'
                        '"confidence":0.9,'
                        '"reason":"用户正在准备开题"}'
                    ),
                    "这是基于 RAG 的回答。",
                ]
            )
            agent = SkillRuntimeAgent(
                llm,
                skills_dir=skills_dir,
                rag_search_tool=rag_tool,
            )

            response = agent.run("工业遮挡定位怎么写开题？")

            answer_context = llm.messages[1][1]["content"]
            self.assertEqual(response, "这是基于 RAG 的回答。")
            self.assertEqual(
                rag_tool.calls,
                [{"query": "工业遮挡定位怎么写开题？", "top_k": 3}],
            )
            self.assertIn("rag_results", answer_context)
            self.assertIn("工业遮挡会影响定位稳定性。", answer_context)

    def test_runtime_handles_markdown_writer_tool_call_and_final_answer(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            skills_dir = tmp_path / "skills"
            output_dir = tmp_path / "outputs"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "opening-report",
                            "confidence": 0.9,
                            "reason": "The user wants an opening report draft.",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_call",
                            "tool_name": "markdown_writer",
                            "arguments": {
                                "file_name": "opening_draft",
                                "content": "# Opening Draft\n\nSaved by the agent.",
                            },
                            "reason": "Save the draft as Markdown.",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "final_answer",
                            "content": "Draft saved to Markdown.",
                        }
                    ),
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)
            tool_registry = ToolRegistry()
            tool_registry.register(MarkdownWriterTool(output_dir=output_dir))
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=tool_registry,
                allowed_tools=["markdown_writer"],
            )
            runs_dir = Path("outputs/runs")
            before = set(runs_dir.iterdir()) if runs_dir.exists() else set()

            response = runtime.run("Please save an opening report draft as Markdown.")

            after = set(runs_dir.iterdir())
            new_runs = list(after - before)
            markdown_path = output_dir / "opening_draft.md"
            self.assertEqual(response, "Draft saved to Markdown.")
            self.assertTrue(markdown_path.exists())
            self.assertEqual(markdown_path.read_text(encoding="utf-8"), "# Opening Draft\n\nSaved by the agent.")
            self.assertEqual(len(new_runs), 1)
            trace = json.loads((new_runs[0] / "trace.json").read_text(encoding="utf-8"))
            event_types = [event["event_type"] for event in trace["events"]]
            self.assertIn("tool_call_requested", event_types)
            self.assertIn("tool_called", event_types)
            self.assertEqual(len(llm.messages), 3)
            observation_prompt = llm.messages[2][1]["content"]
            self.assertIn("tool_result", observation_prompt)
            self.assertIn("opening_draft.md", observation_prompt)

    def test_runtime_saves_final_answer_after_tool_call_to_session_memory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            skills_dir = tmp_path / "skills"
            output_dir = tmp_path / "outputs"
            memory_file = tmp_path / "session.json"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "opening-report",
                            "confidence": 0.9,
                            "reason": "The user wants an opening report draft.",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_call",
                            "tool_name": "markdown_writer",
                            "arguments": {
                                "file_name": "opening_draft",
                                "content": "# Opening Draft",
                            },
                            "reason": "Save the draft as Markdown.",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "final_answer",
                            "content": "Draft saved to Markdown.",
                        }
                    ),
                ]
            )
            memory = SessionMemory(file_path=memory_file)
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir, session_memory=memory)
            tool_registry = ToolRegistry()
            tool_registry.register(MarkdownWriterTool(output_dir=output_dir))
            runtime = YCAgentRuntime(
                agent,
                expects_json=True,
                tool_registry=tool_registry,
                allowed_tools=["markdown_writer"],
            )

            response = runtime.run("Please save an opening report draft as Markdown.")

            saved_messages = json.loads(memory_file.read_text(encoding="utf-8"))
            self.assertEqual(response, "Draft saved to Markdown.")
            self.assertEqual(saved_messages[-1]["content"], "Draft saved to Markdown.")
            self.assertNotIn("tool_call", saved_messages[-1]["content"])


    def test_run_answers_with_selected_skill_body(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    (
                        '{"type":"skill_selection",'
                        '"selected_skill":"opening-report",'
                        '"confidence":0.9,'
                        '"reason":"用户正在准备开题"}'
                    ),
                    "这是基于开题报告 Skill 的回答。",
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)

            response = agent.run("帮我准备开题")

            self.assertEqual(response, "这是基于开题报告 Skill 的回答。")
            self.assertEqual(len(llm.messages), 2)
            answer_system_prompt = llm.messages[1][0]["content"]
            self.assertIn("tool_call", answer_system_prompt)
            self.assertIn("markdown_writer", answer_system_prompt)
            answer_context = llm.messages[1][1]["content"]
            self.assertIn("开题报告 Skill", answer_context)
            self.assertIn("opening-report", answer_context)

    def test_run_retries_when_skill_execution_repeats_skill_selection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "opening-report",
                            "confidence": 0.95,
                            "reason": "用户请求准备开题报告",
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "type": "skill_selection",
                            "selected_skill": "opening-report",
                            "confidence": 0.95,
                            "reason": "错误地重复了选 Skill 阶段",
                        },
                        ensure_ascii=False,
                    ),
                    "开题报告目录结构：\n\n1. 研究背景\n2. 研究目标\n3. 技术路线",
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)

            response = agent.run("帮我准备开题报告，先给我一个目录结构")

            self.assertIn("开题报告目录结构", response)
            self.assertEqual(len(llm.messages), 3)
            retry_prompt = llm.messages[2][0]["content"]
            self.assertIn("不要再输出 skill_selection", retry_prompt)

    def test_run_falls_back_to_plain_answer_when_no_skill_selected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    (
                        '{"type":"skill_selection",'
                        '"selected_skill":null,'
                        '"confidence":0.2,'
                        '"reason":"没有合适 Skill"}'
                    ),
                    "普通回答",
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)

            response = agent.run("你好")

            self.assertEqual(response, "普通回答")
            self.assertEqual(len(llm.messages), 2)

    def test_runtime_writes_trace_for_skill_runtime_agent(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "skills"
            write_skill(skills_dir)
            llm = FakeLLM(
                [
                    (
                        '{"type":"skill_selection",'
                        '"selected_skill":"opening-report",'
                        '"confidence":0.9,'
                        '"reason":"用户正在准备开题"}'
                    ),
                    "这是基于开题报告 Skill 的回答。",
                ]
            )
            agent = SkillRuntimeAgent(llm, skills_dir=skills_dir)
            runtime = YCAgentRuntime(agent)
            runs_dir = Path("outputs/runs")
            before = set(runs_dir.iterdir()) if runs_dir.exists() else set()

            response = runtime.run("帮我准备开题")

            after = set(runs_dir.iterdir())
            new_runs = list(after - before)
            self.assertEqual(response, "这是基于开题报告 Skill 的回答。")
            self.assertEqual(len(new_runs), 1)
            self.assertTrue((new_runs[0] / "input.md").exists())
            self.assertTrue((new_runs[0] / "final_output.md").exists())
            self.assertTrue((new_runs[0] / "trace.json").exists())


if __name__ == "__main__":
    unittest.main()
