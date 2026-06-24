import unittest

from yc_agents.intent.semantic_matcher import SemanticIntentMatcher
from yc_agents.skills.definition import SkillDefinition


class TestSemanticIntentMatcher(unittest.TestCase):
    def test_match_scores_skill_by_text_overlap(self):
        skills = [
            SkillDefinition(
                name="document-format-normalizer",
                description="Word 文档 格式 调整 模板 docx",
                allowed_tools=[],
                body="",
                path="skills/document-format-normalizer",
            ),
            SkillDefinition(
                name="other-skill",
                description="聊天 问答 闲聊",
                allowed_tools=[],
                body="",
                path="skills/other-skill",
            ),
        ]

        matches = SemanticIntentMatcher().match("Word 文档格式怎么按模板调整", skills)

        self.assertEqual(matches[0]["skill_name"], "document-format-normalizer")
        self.assertGreater(matches[0]["confidence"], matches[1]["confidence"])
        self.assertIn("overlap_terms", matches[0])

    def test_match_returns_empty_list_for_empty_input(self):
        skills = [
            SkillDefinition(
                name="document-format-normalizer",
                description="Word 文档格式调整",
                allowed_tools=[],
                body="",
                path="skills/document-format-normalizer",
            )
        ]

        matches = SemanticIntentMatcher().match("", skills)

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
