import unittest

from yc_agents.intent.semantic_matcher import SemanticIntentMatcher
from yc_agents.skills.definition import SkillDefinition


class TestSemanticIntentMatcher(unittest.TestCase):
    def test_match_scores_skill_by_text_overlap(self):
        skills = [
            SkillDefinition(
                name="code-review",
                description="project architecture risk review",
                allowed_tools=[],
                body="",
                path="skills/code-review",
            ),
            SkillDefinition(
                name="other-skill",
                description="chat casual conversation",
                allowed_tools=[],
                body="",
                path="skills/other-skill",
            ),
        ]

        matches = SemanticIntentMatcher().match(
            "review project architecture risks",
            skills,
        )

        self.assertEqual(matches[0]["skill_name"], "code-review")
        self.assertGreater(matches[0]["confidence"], matches[1]["confidence"])
        self.assertIn("overlap_terms", matches[0])

    def test_match_returns_empty_list_for_empty_input(self):
        skills = [
            SkillDefinition(
                name="code-review",
                description="Project architecture review",
                allowed_tools=[],
                body="",
                path="skills/code-review",
            )
        ]

        matches = SemanticIntentMatcher().match("", skills)

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
