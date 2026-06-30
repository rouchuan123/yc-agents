import json
import unittest

from yc_agents.harness.json_protocol import InvalidModelJSONError
from yc_agents.intent.llm_classifier import LLMIntentClassifier
from yc_agents.skills.definition import SkillDefinition


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.messages = []

    def think(self, messages):
        self.messages.append(messages)
        return self.response


class FakeJSONLLM:
    def __init__(self, response):
        self.response = response
        self.think_calls = []
        self.think_json_calls = []

    def think(self, messages):
        self.think_calls.append(messages)
        return self.response

    def think_json(self, messages):
        self.think_json_calls.append(messages)
        return self.response


class TestLLMIntentClassifier(unittest.TestCase):
    def test_classify_returns_skill_selection_json(self):
        llm = FakeLLM(
            json.dumps(
                {
                    "type": "skill_selection",
                    "selected_skill": "code-review",
                    "confidence": 0.9,
                    "reason": "User asked for a project review",
                },
                ensure_ascii=False,
            )
        )
        skills = [
            SkillDefinition(
                name="code-review",
                description="Review project architecture and risks.",
                allowed_tools=[],
                body="",
                path="skills/code-review",
            )
        ]

        result = LLMIntentClassifier(llm).classify("review this project", skills)

        self.assertEqual(result["selected_skill"], "code-review")
        self.assertEqual(result["confidence"], 0.9)
        self.assertEqual(len(llm.messages), 1)
        prompt = llm.messages[0][1]["content"]
        self.assertIn("review this project", prompt)
        self.assertIn("code-review", prompt)

    def test_classify_rejects_invalid_json(self):
        llm = FakeLLM("not JSON")

        with self.assertRaises(InvalidModelJSONError):
            LLMIntentClassifier(llm).classify("hello", [])

    def test_classify_prefers_think_json_for_protocol_output(self):
        llm = FakeJSONLLM(
            json.dumps(
                {
                    "type": "skill_selection",
                    "selected_skill": None,
                    "confidence": 0.1,
                    "reason": "No skill needed",
                },
                ensure_ascii=False,
            )
        )

        result = LLMIntentClassifier(llm).classify("hello", [])

        self.assertIsNone(result["selected_skill"])
        self.assertEqual(len(llm.think_json_calls), 1)
        self.assertEqual(llm.think_calls, [])


if __name__ == "__main__":
    unittest.main()
