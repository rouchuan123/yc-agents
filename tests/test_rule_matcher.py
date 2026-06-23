import unittest

from yc_agents.intent.rule_matcher import RuleIntentMatcher
from yc_agents.skills.definition import SkillDefinition


class TestRuleIntentMatcher(unittest.TestCase):
    def test_match_opening_report_by_keywords(self):
        skills = [
            SkillDefinition(
                name="opening-report",
                description="Use for 开题 报告 proposal tasks.",
                allowed_tools=[],
                body="",
                path="skills/opening-report",
            ),
            SkillDefinition(
                name="literature-review",
                description="Use for 文献 综述 literature review tasks.",
                allowed_tools=[],
                body="",
                path="skills/literature-review",
            ),
        ]

        matches = RuleIntentMatcher().match("帮我准备开题报告", skills)

        self.assertEqual(matches[0]["skill_name"], "opening-report")
        self.assertGreater(matches[0]["confidence"], 0)
        self.assertIn("开题", matches[0]["matched_keywords"])

    def test_match_returns_empty_list_when_no_keywords_match(self):
        skills = [
            SkillDefinition(
                name="opening-report",
                description="Use for 开题 报告 proposal tasks.",
                allowed_tools=[],
                body="",
                path="skills/opening-report",
            )
        ]

        matches = RuleIntentMatcher().match("今天天气怎么样", skills)

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
