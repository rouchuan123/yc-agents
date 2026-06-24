import unittest

from yc_agents.intent.rule_matcher import RuleIntentMatcher
from yc_agents.skills.definition import SkillDefinition


class TestRuleIntentMatcher(unittest.TestCase):
    def test_match_document_format_normalizer_by_keywords(self):
        skills = [
            SkillDefinition(
                name="document-format-normalizer",
                description="用于 Word 文档格式调整",
                allowed_tools=[],
                body="",
                path="skills/document-format-normalizer",
            )
        ]

        matches = RuleIntentMatcher().match("帮我把 draft.docx 按模板调整格式", skills)

        self.assertEqual(matches[0]["skill_name"], "document-format-normalizer")
        self.assertGreater(matches[0]["confidence"], 0)
        self.assertIn("docx", matches[0]["matched_keywords"])
        self.assertIn("格式", matches[0]["matched_keywords"])

    def test_match_returns_empty_list_when_no_keywords_match(self):
        skills = [
            SkillDefinition(
                name="document-format-normalizer",
                description="用于 Word 文档格式调整",
                allowed_tools=[],
                body="",
                path="skills/document-format-normalizer",
            )
        ]

        matches = RuleIntentMatcher().match("今天天气怎么样", skills)

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
