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
                    "selected_skill": "opening-report",
                    "confidence": 0.9,
                    "reason": "用户正在准备开题报告",
                },
                ensure_ascii=False,
            )
        )
        skills = [
            SkillDefinition(
                name="opening-report",
                description="Help with opening reports.",
                allowed_tools=[],
                body="",
                path="skills/opening-report",
            )
        ]

        result = LLMIntentClassifier(llm).classify("帮我准备开题", skills)

        self.assertEqual(result["selected_skill"], "opening-report")
        self.assertEqual(result["confidence"], 0.9)
        self.assertEqual(len(llm.messages), 1)
        prompt = llm.messages[0][1]["content"]
        self.assertIn("帮我准备开题", prompt)
        self.assertIn("opening-report", prompt)

    def test_classify_rejects_invalid_json(self):
        llm = FakeLLM("这不是 JSON")

        with self.assertRaises(InvalidModelJSONError):
            LLMIntentClassifier(llm).classify("你好", [])


if __name__ == "__main__":
    unittest.main()
