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


if __name__ == "__main__":
    unittest.main()
