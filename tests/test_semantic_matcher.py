import unittest

from yc_agents.intent.semantic_matcher import SemanticIntentMatcher
from yc_agents.skills.definition import SkillDefinition


class TestSemanticIntentMatcher(unittest.TestCase):
    def test_match_scores_skill_by_text_overlap(self):
        skills = [
            SkillDefinition(
                name="opening-report",
                description="开题 报告 研究 背景 技术路线",
                allowed_tools=[],
                body="",
                path="skills/opening-report",
            ),
            SkillDefinition(
                name="thesis-system-design",
                description="系统 设计 接口 数据库 Spring Boot",
                allowed_tools=[],
                body="",
                path="skills/thesis-system-design",
            ),
        ]

        matches = SemanticIntentMatcher().match("研究背景和技术路线怎么写", skills)

        self.assertEqual(matches[0]["skill_name"], "opening-report")
        self.assertGreater(matches[0]["confidence"], matches[1]["confidence"])
        self.assertIn("overlap_terms", matches[0])

    def test_match_returns_empty_list_for_empty_input(self):
        skills = [
            SkillDefinition(
                name="opening-report",
                description="开题 报告",
                allowed_tools=[],
                body="",
                path="skills/opening-report",
            )
        ]

        matches = SemanticIntentMatcher().match("", skills)

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
