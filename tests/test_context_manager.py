import unittest

from yc_agents.harness.context_manager import ContextManager
from yc_agents.skills.definition import SkillDefinition


class TestContextManager(unittest.TestCase):
    def test_build_skill_selection_context(self):
        skill = SkillDefinition(
            name="opening-report",
            description="Help with opening report.",
            allowed_tools=["rag_search"],
            body="long body",
            path="skills/opening-report",
        )

        result = ContextManager().build_skill_selection_context(
            "帮我准备开题",
            [skill],
        )

        self.assertEqual(result["task"], "skill_selection")
        self.assertEqual(result["user_input"], "帮我准备开题")
        self.assertEqual(
            result["skills"],
            [
                {
                    "name": "opening-report",
                    "description": "Help with opening report.",
                    "allowed_tools": ["rag_search"],
                }
            ],
        )

    def test_build_skill_selection_context_includes_three_level_memory(self):
        result = ContextManager().build_skill_selection_context(
            "继续完善系统方案",
            [],
            memory_context={
                "session": [
                    {"role": "user", "content": "上一轮问题"},
                    {"role": "assistant", "content": "上一轮回答"},
                ],
                "summary": "阶段摘要：已经完成 Skill Runtime MVP。",
                "profile": {
                    "major": "通信工程",
                    "research_direction": "工业遮挡失联场景定位",
                },
            },
        )

        self.assertEqual(
            result["memory"],
            {
                "session": [
                    {"role": "user", "content": "上一轮问题"},
                    {"role": "assistant", "content": "上一轮回答"},
                ],
                "summary": "阶段摘要：已经完成 Skill Runtime MVP。",
                "profile": {
                    "major": "通信工程",
                    "research_direction": "工业遮挡失联场景定位",
                },
            },
        )
        self.assertEqual(result["recent_messages"], result["memory"]["session"])

    def test_build_memory_context_uses_empty_defaults(self):
        result = ContextManager().build_memory_context()

        self.assertEqual(
            result,
            {
                "session": [],
                "summary": "",
                "profile": {},
            },
        )

    def test_build_memory_context_compresses_session_when_threshold_reached(self):
        class FakeCompressor:
            def __init__(self):
                self.received_messages = None

            def compress_and_save(self, messages):
                self.received_messages = messages
                return "压缩后的阶段摘要"

        messages = [
            {"role": "user", "content": "问题 1"},
            {"role": "assistant", "content": "回答 1"},
            {"role": "user", "content": "问题 2"},
        ]
        compressor = FakeCompressor()

        result = ContextManager().build_memory_context(
            session=messages,
            summary="旧摘要",
            memory_compressor=compressor,
            compression_threshold=3,
        )

        self.assertEqual(result["summary"], "压缩后的阶段摘要")
        self.assertEqual(compressor.received_messages, messages)

    def test_build_memory_context_keeps_summary_when_below_threshold(self):
        class FakeCompressor:
            def compress_and_save(self, messages):
                raise AssertionError("compressor should not be called")

        result = ContextManager().build_memory_context(
            session=[{"role": "user", "content": "问题 1"}],
            summary="旧摘要",
            memory_compressor=FakeCompressor(),
            compression_threshold=3,
        )

        self.assertEqual(result["summary"], "旧摘要")

    def test_build_skill_execution_context_includes_rag_results(self):
        skill = SkillDefinition(
            name="opening-report",
            description="Help with opening report.",
            allowed_tools=["rag_search"],
            body="long body",
            path="skills/opening-report",
        )
        rag_results = [
            {
                "source": "paper.md",
                "chunk_id": 0,
                "score": 2,
                "text": "工业遮挡会影响定位稳定性。",
            }
        ]

        result = ContextManager().build_skill_execution_context(
            user_input="工业遮挡定位怎么写开题？",
            selected_skill=skill,
            selection={"selected_skill": "opening-report"},
            memory_context={"session": [], "summary": "", "profile": {}},
            rag_results=rag_results,
        )

        self.assertEqual(result["task"], "skill_execution")
        self.assertEqual(result["selected_skill"]["name"], "opening-report")
        self.assertEqual(result["rag_results"], rag_results)


if __name__ == "__main__":
    unittest.main()
