import unittest

from yc_agents.intent.router import IntentRouter
from yc_agents.skills.definition import SkillDefinition


class FakeRuleMatcher:
    def match(self, user_input, skills):
        return [
            {
                "skill_name": "document-format-normalizer",
                "confidence": 1.0,
                "reason": "规则命中文档格式调整",
            }
        ]


class FakeSemanticMatcher:
    def match(self, user_input, skills):
        return [
            {
                "skill_name": "document-format-normalizer",
                "confidence": 0.7,
                "reason": "语义更像 Word 格式调整",
            },
            {
                "skill_name": "other-skill",
                "confidence": 0.1,
                "reason": "语义少量命中",
            },
        ]


class FakeLLMClassifier:
    def classify(self, user_input, skills):
        return {
            "type": "skill_selection",
            "selected_skill": "document-format-normalizer",
            "confidence": 0.9,
            "reason": "LLM 判断用户要调整 Word 文档格式",
        }


class TestIntentRouter(unittest.TestCase):
    def test_route_selects_highest_weighted_skill(self):
        skills = [
            SkillDefinition(
                name="document-format-normalizer",
                description="Word 文档格式调整",
                allowed_tools=[],
                body="",
                path="skills/document-format-normalizer",
            ),
            SkillDefinition(
                name="other-skill",
                description="其他能力",
                allowed_tools=[],
                body="",
                path="skills/other-skill",
            ),
        ]

        result = IntentRouter(
            rule_matcher=FakeRuleMatcher(),
            semantic_matcher=FakeSemanticMatcher(),
            llm_classifier=FakeLLMClassifier(),
        ).route("帮我调整 draft.docx 的格式", skills)

        self.assertEqual(result["type"], "intent_route")
        self.assertEqual(result["selected_skill"], "document-format-normalizer")
        self.assertAlmostEqual(result["confidence"], 0.855)
        self.assertEqual(
            result["candidates"][0]["skill_name"],
            "document-format-normalizer",
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
