import unittest

from yc_agents.harness.json_protocol import InvalidModelJSONError
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


class InvalidJSONLLMClassifier:
    def classify(self, user_input, skills):
        raise InvalidModelJSONError(
            "Model output is not valid JSON: Expecting value",
            raw_text="",
        )


class NetworkErrorLLMClassifier:
    def classify(self, user_input, skills):
        raise ConnectionError("provider unreachable")


class CountingLLMClassifier:
    def __init__(self):
        self.calls = 0

    def classify(self, user_input, skills):
        self.calls += 1
        return {
            "type": "skill_selection",
            "selected_skill": "code-review",
            "confidence": 0.9,
            "reason": "LLM selected project review",
        }


class WeakSemanticMatcher:
    def match(self, user_input, skills):
        return [
            {"skill_name": "code-review", "confidence": 0.6, "reason": "weak"},
            {"skill_name": "other-skill", "confidence": 0.5, "reason": "weak"},
        ]


class CloseRuleMatcher:
    def match(self, user_input, skills):
        return [
            {"skill_name": "code-review", "confidence": 1.0, "reason": "close"},
            {"skill_name": "other-skill", "confidence": 0.9, "reason": "close"},
        ]


class CloseSemanticMatcher:
    def match(self, user_input, skills):
        return [
            {"skill_name": "code-review", "confidence": 0.8, "reason": "close"},
            {"skill_name": "other-skill", "confidence": 0.75, "reason": "close"},
        ]


class EmptyMatcher:
    def match(self, user_input, skills):
        return []


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

    def _skills(self):
        return [
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

    def test_route_degrades_when_llm_classifier_returns_invalid_json(self):
        result = IntentRouter(
            rule_matcher=FakeRuleMatcher(),
            semantic_matcher=FakeSemanticMatcher(),
            llm_classifier=InvalidJSONLLMClassifier(),
        ).route("review this project", skills=self._skills())

        self.assertEqual(result["selected_skill"], "code-review")
        self.assertEqual(result["candidates"][0]["components"]["llm"], 0.0)
        self.assertIn("llm_error", result)
        self.assertIn("not valid JSON", result["llm_error"])

    def test_route_degrades_when_llm_classifier_raises_provider_error(self):
        result = IntentRouter(
            rule_matcher=FakeRuleMatcher(),
            semantic_matcher=FakeSemanticMatcher(),
            llm_classifier=NetworkErrorLLMClassifier(),
        ).route("review this project", skills=self._skills())

        self.assertEqual(result["selected_skill"], "code-review")
        self.assertEqual(result["candidates"][0]["components"]["llm"], 0.0)
        self.assertIn("provider unreachable", result["llm_error"])

    def test_route_skips_llm_when_rule_and_semantic_lead_is_decisive(self):
        classifier = CountingLLMClassifier()

        result = IntentRouter(
            rule_matcher=FakeRuleMatcher(),
            semantic_matcher=FakeSemanticMatcher(),
            llm_classifier=classifier,
        ).route("review this project", self._skills(), allow_llm_skip=True)

        self.assertEqual(classifier.calls, 0)
        self.assertTrue(result["llm_skipped"])
        self.assertEqual(result["selected_skill"], "code-review")
        self.assertEqual(result["candidates"][0]["components"]["llm"], 0.0)
        self.assertAlmostEqual(result["confidence"], 0.495)

    def test_route_keeps_llm_when_fused_score_is_below_threshold(self):
        classifier = CountingLLMClassifier()

        result = IntentRouter(
            rule_matcher=EmptyMatcher(),
            semantic_matcher=WeakSemanticMatcher(),
            llm_classifier=classifier,
        ).route("review this project", self._skills(), allow_llm_skip=True)

        self.assertEqual(classifier.calls, 1)
        self.assertNotIn("llm_skipped", result)
        self.assertEqual(result["candidates"][0]["components"]["llm"], 0.9)

    def test_route_keeps_llm_when_runner_up_is_close(self):
        classifier = CountingLLMClassifier()

        result = IntentRouter(
            rule_matcher=CloseRuleMatcher(),
            semantic_matcher=CloseSemanticMatcher(),
            llm_classifier=classifier,
        ).route("review this project", self._skills(), allow_llm_skip=True)

        self.assertEqual(classifier.calls, 1)
        self.assertNotIn("llm_skipped", result)

    def test_route_llm_skip_is_disabled_by_default(self):
        classifier = CountingLLMClassifier()

        IntentRouter(
            rule_matcher=FakeRuleMatcher(),
            semantic_matcher=FakeSemanticMatcher(),
            llm_classifier=classifier,
        ).route("review this project", self._skills())

        self.assertEqual(classifier.calls, 1)


if __name__ == "__main__":
    unittest.main()
