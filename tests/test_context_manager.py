import unittest

from yc_agents.harness.context_manager import ContextManager
from yc_agents.skills.definition import SkillDefinition


def make_skill():
    return SkillDefinition(
        name="document-format-normalizer",
        description="Word 文档格式调整",
        allowed_tools=["docx_format_normalizer"],
        body="完整技能正文",
        path="skills/document-format-normalizer",
    )


class TestContextManager(unittest.TestCase):
    def test_build_skill_selection_context(self):
        result = ContextManager().build_skill_selection_context(
            "帮我调整 draft.docx 的格式",
            [make_skill()],
        )

        self.assertEqual(result["task"], "skill_selection")
        self.assertEqual(result["user_input"], "帮我调整 draft.docx 的格式")
        self.assertEqual(
            result["skills"],
            [
                {
                    "name": "document-format-normalizer",
                    "description": "Word 文档格式调整",
                    "triggers": [],
                    "inputs": [],
                    "outputs": [],
                    "allowed_tools": ["docx_format_normalizer"],
                }
            ],
        )

    def test_build_skill_selection_context_includes_memory_and_workspace(self):
        memory = {
            "session": [{"role": "user", "content": "上一轮问题"}],
            "summary": "已经选择文档格式调整方向",
            "profile": {"preferred_template": "report-standard"},
        }

        result = ContextManager().build_skill_selection_context(
            "继续处理",
            [make_skill()],
            memory_context=memory,
            workspace_context={"path": r"E:\paper"},
        )

        self.assertEqual(result["memory"], memory)
        self.assertEqual(result["recent_messages"], memory["session"])
        self.assertEqual(result["workspace"]["path"], r"E:\paper")

    def test_build_memory_context_compresses_session_when_threshold_reached(self):
        class FakeCompressor:
            def __init__(self):
                self.received_messages = None

            def compress_and_save(self, messages):
                self.received_messages = messages
                return "压缩后的摘要"

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

        self.assertEqual(result["summary"], "压缩后的摘要")
        self.assertEqual(compressor.received_messages, messages)

    def test_build_skill_execution_context_includes_selected_skill_and_rag(self):
        rag_results = [{"source": "template.md", "text": "report-standard"}]

        result = ContextManager().build_skill_execution_context(
            user_input="调整格式",
            selected_skill=make_skill(),
            selection={"selected_skill": "document-format-normalizer"},
            memory_context={"session": [], "summary": "", "profile": {}},
            rag_results=rag_results,
        )

        self.assertEqual(result["task"], "skill_execution")
        self.assertEqual(result["selected_skill"]["name"], "document-format-normalizer")
        self.assertEqual(result["rag_results"], rag_results)


if __name__ == "__main__":
    unittest.main()
