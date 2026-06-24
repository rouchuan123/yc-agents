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
                    "selected_skill": "document-format-normalizer",
                    "confidence": 0.9,
                    "reason": "用户正在处理 Word 文档格式调整",
                },
                ensure_ascii=False,
            )
        )
        skills = [
            SkillDefinition(
                name="document-format-normalizer",
                description="Help normalize Word documents.",
                allowed_tools=[],
                body="",
                path="skills/document-format-normalizer",
            )
        ]

        result = LLMIntentClassifier(llm).classify("帮我调整 Word 格式", skills)

        self.assertEqual(result["selected_skill"], "document-format-normalizer")
        self.assertEqual(result["confidence"], 0.9)
        self.assertEqual(len(llm.messages), 1)
        prompt = llm.messages[0][1]["content"]
        self.assertIn("帮我调整 Word 格式", prompt)
        self.assertIn("document-format-normalizer", prompt)

    def test_classify_rejects_invalid_json(self):
        llm = FakeLLM("这不是 JSON")

        with self.assertRaises(InvalidModelJSONError):
            LLMIntentClassifier(llm).classify("你好", [])


if __name__ == "__main__":
    unittest.main()
