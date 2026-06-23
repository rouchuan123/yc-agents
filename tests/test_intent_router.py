import unittest

from yc_agents.intent.router import IntentRouter
from yc_agents.skills.definition import SkillDefinition


class FakeRuleMatcher:
    def match(self, user_input, skills):
        return [
            {
                "skill_name": "literature-review",
                "confidence": 1.0,
                "reason": "规则更像文献综述",
            }
        ]


class FakeSemanticMatcher:
    def match(self, user_input, skills):
        return [
            {
                "skill_name": "opening-report",
                "confidence": 0.7,
                "reason": "语义更像开题报告",
            },
            {
                "skill_name": "literature-review",
                "confidence": 0.1,
                "reason": "语义少量命中文献综述",
            },
        ]


class FakeLLMClassifier:
    def classify(self, user_input, skills):
        return {
            "type": "skill_selection",
            "selected_skill": "opening-report",
            "confidence": 0.9,
            "reason": "LLM 判断用户在准备开题",
        }


class TestIntentRouter(unittest.TestCase):
    def test_route_selects_highest_weighted_skill(self):
        skills = [
            SkillDefinition(
                name="opening-report",
                description="开题报告",
                allowed_tools=[],
                body="",
                path="skills/opening-report",
            ),
            SkillDefinition(
                name="literature-review",
                description="文献综述",
                allowed_tools=[],
                body="",
                path="skills/literature-review",
            ),
        ]

        result = IntentRouter(
            rule_matcher=FakeRuleMatcher(),
            semantic_matcher=FakeSemanticMatcher(),
            llm_classifier=FakeLLMClassifier(),
        ).route("帮我准备开题报告", skills)

        self.assertEqual(result["type"], "intent_route")
        self.assertEqual(result["selected_skill"], "opening-report")
        self.assertAlmostEqual(result["confidence"], 0.605)
        self.assertEqual(result["candidates"][0]["skill_name"], "opening-report")
        self.assertEqual(
            result["candidates"][0]["components"],
            {
                "rule": 0.0,
                "semantic": 0.7,
                "llm": 0.9,
            },
        )
        self.assertEqual(
            result["candidates"][0]["weighted_scores"],
            {
                "rule": 0.0,
                "semantic": 0.245,
                "llm": 0.36,
            },
        )


if __name__ == "__main__":
    unittest.main()
