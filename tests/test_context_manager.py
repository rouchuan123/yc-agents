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


if __name__ == "__main__":
    unittest.main()