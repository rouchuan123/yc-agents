import unittest

from yc_agents.intent.rule_matcher import RuleIntentMatcher
from yc_agents.skills.definition import SkillDefinition


class TestRuleIntentMatcher(unittest.TestCase):
    def test_match_code_review_by_keywords(self):
        skills = [
            SkillDefinition(
                name="code-review",
                description="Project architecture and risk review",
                allowed_tools=[],
                body="",
                path="skills/code-review",
            )
        ]

        matches = RuleIntentMatcher().match(
            "please review this project architecture and risks",
            skills,
        )

        self.assertEqual(matches[0]["skill_name"], "code-review")
        self.assertGreater(matches[0]["confidence"], 0)
        self.assertIn("review", matches[0]["matched_keywords"])
        self.assertIn("architecture", matches[0]["matched_keywords"])

    def test_match_returns_empty_list_when_no_keywords_match(self):
        skills = [
            SkillDefinition(
                name="code-review",
                description="Project architecture and risk review",
                allowed_tools=[],
                body="",
                path="skills/code-review",
            )
        ]

        matches = RuleIntentMatcher().match("how is the weather today?", skills)

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
