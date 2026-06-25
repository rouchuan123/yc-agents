import unittest

from yc_agents.intent.router import IntentRouter
from yc_agents.skills.definition import SkillDefinition


class FakeRuleMatcher:
    def match(self, user_input, skills):
        return [
            {
                "skill_name": "code-review",
                "confidence": 1.0,
                "reason": "rule matched project review",
            }
        ]


class FakeSemanticMatcher:
    def match(self, user_input, skills):
        return [
            {
                "skill_name": "code-review",
                "confidence": 0.7,
                "reason": "semantic match for architecture review",
            },
            {
                "skill_name": "other-skill",
                "confidence": 0.1,
                "reason": "weak semantic match",
            },
        ]


class FakeLLMClassifier:
    def classify(self, user_input, skills):
        return {
            "type": "skill_selection",
            "selected_skill": "code-review",
            "confidence": 0.9,
            "reason": "LLM selected project review",
        }


class TestIntentRouter(unittest.TestCase):
    def test_route_selects_highest_weighted_skill(self):
        skills = [
            SkillDefinition(
                name="code-review",
                description="Project architecture review",
                allowed_tools=[],
                body="",
                path="skills/code-review",
            ),
            SkillDefinition(
                name="other-skill",
                description="Other capability",
                allowed_tools=[],
                body="",
                path="skills/other-skill",
            ),
        ]

        result = IntentRouter(
            rule_matcher=FakeRuleMatcher(),
            semantic_matcher=FakeSemanticMatcher(),
            llm_classifier=FakeLLMClassifier(),
        ).route("review this project", skills)

        self.assertEqual(result["type"], "intent_route")
        self.assertEqual(result["selected_skill"], "code-review")
        self.assertAlmostEqual(result["confidence"], 0.855)
        self.assertEqual(
            result["candidates"][0]["skill_name"],
            "code-review",
        )
        self.assertEqual(
            result["candidates"][0]["components"],
            {
                "rule": 1.0,
                "semantic": 0.7,
                "llm": 0.9,
            },
        )


if __name__ == "__main__":
    unittest.main()
