import unittest

from yc_agents.harness.context_report import build_context_report
from yc_agents.harness.context_manager import ContextManager
from yc_agents.memory.compressor import MemoryCompressor
from yc_agents.skills.definition import SkillDefinition


def make_skill():
    return SkillDefinition(
        name="code-review",
        description="Project architecture review",
        allowed_tools=["workspace_files", "file_reader"],
        body="Complete skill body",
        path="skills/code-review",
    )


class SummarySkill:
    name = "eval-writer"
    description = "Writes eval plans."
    allowed_tools = []

    def to_summary(self):
        return {"name": self.name, "description": self.description, "allowed_tools": []}


class TestContextManager(unittest.TestCase):
    def test_build_context_report_summarizes_sections(self):
        context = {
            "user_input": "请总结项目",
            "memory": {
                "session": [{"role": "user", "content": "上一轮问题"}],
                "summary": "阶段摘要",
                "profile": {"language": "zh-CN"},
            },
            "workspace": {"root": "E:/code/yc-agents"},
            "skills": [{"name": "eval-writer"}],
        }

        report = build_context_report(context, max_tokens=200)

        self.assertEqual(report["max_tokens"], 200)
        self.assertGreater(report["total_estimated_tokens"], 0)
        self.assertTrue(
            set(report["sections"]) >= {"user_input", "memory", "workspace", "skills"}
        )
        self.assertFalse(report["over_budget"])

    def test_build_skill_selection_context(self):
        result = ContextManager().build_skill_selection_context(
            "review this project",
            [make_skill()],
        )

        self.assertEqual(result["task"], "skill_selection")
        self.assertEqual(result["user_input"], "review this project")
        self.assertEqual(
            result["skills"],
            [
                {
                    "name": "code-review",
                    "description": "Project architecture review",
                    "triggers": [],
                    "inputs": [],
                    "outputs": [],
                }
            ],
        )

    def test_build_skill_selection_context_includes_memory_and_workspace(self):
        memory = {
            "session": [{"role": "user", "content": "previous question"}],
            "summary": "Already discussed project structure",
            "profile": {"preferred_output": "concise"},
        }

        result = ContextManager().build_skill_selection_context(
            "continue",
            [make_skill()],
            memory_context=memory,
            workspace_context={"path": r"E:\project"},
        )

        self.assertEqual(result["memory"], memory)
        self.assertNotIn("recent_messages", result)
        self.assertEqual(result["workspace"]["path"], r"E:\project")

    def test_skill_selection_context_can_include_context_report(self):
        manager = ContextManager()

        context = manager.build_skill_selection_context(
            user_input="帮我写 eval",
            skills=[SummarySkill()],
            memory_messages=[{"role": "user", "content": "之前的问题"}],
            include_context_report=True,
            context_budget_tokens=1000,
        )

        self.assertEqual(context["context_report"]["max_tokens"], 1000)
        self.assertIn("skills", context["context_report"]["sections"])

    def test_memory_compressor_returns_summary_with_metadata(self):
        compressor = MemoryCompressor(max_items=2)
        messages = [
            {"role": "user", "content": "问题 1"},
            {"role": "assistant", "content": "回答 1"},
            {"role": "user", "content": "问题 2"},
        ]

        result = compressor.compress_messages_with_metadata(messages)

        self.assertEqual(result["compressed_count"], 1)
        self.assertEqual(result["kept_count"], 2)
        self.assertIn("问题 2", result["summary"])

    def test_build_skill_execution_context_includes_selected_skill_and_rag(self):
        rag_results = [{"source": "notes.md", "text": "architecture"}]

        result = ContextManager().build_skill_execution_context(
            user_input="summarize architecture",
            selected_skill=make_skill(),
            selection={"selected_skill": "code-review"},
            memory_context={"session": [], "summary": "", "profile": {}},
            rag_results=rag_results,
        )

        self.assertEqual(result["task"], "skill_execution")
        self.assertEqual(result["selected_skill"]["name"], "code-review")
        self.assertEqual(result["rag_results"], rag_results)


if __name__ == "__main__":
    unittest.main()
