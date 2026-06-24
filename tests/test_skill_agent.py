import unittest

from yc_agents.agents.skill_agent import SkillAgent


class FakeLLM:
    def __init__(self):
        self.messages = None

    def think(self, messages):
        self.messages = messages
        return (
            '{"type":"skill_selection",'
            '"selected_skill":"document-format-normalizer",'
            '"confidence":0.9,'
            '"reason":"用户需要调整 Word 文档格式"}'
        )


class TestSkillAgent(unittest.TestCase):
    def test_select_skill_returns_model_json_text(self):
        llm = FakeLLM()
        agent = SkillAgent(llm)

        context = {
            "task": "skill_selection",
            "user_input": "帮我调整 draft.docx 的格式",
            "skills": [
                {
                    "name": "document-format-normalizer",
                    "description": "Word 文档格式调整",
                    "allowed_tools": ["docx_format_normalizer"],
                }
            ],
        }

        result = agent.select_skill(context)

        self.assertIn('"type":"skill_selection"', result)
        self.assertIn('"selected_skill":"document-format-normalizer"', result)

    def test_select_skill_sends_context_to_llm(self):
        llm = FakeLLM()
        agent = SkillAgent(llm)

        context = {
            "task": "skill_selection",
            "user_input": "帮我调整 Word 格式",
            "skills": [
                {
                    "name": "document-format-normalizer",
                    "description": "Word 文档格式调整",
                    "allowed_tools": [],
                }
            ],
        }

        agent.select_skill(context)

        self.assertEqual(llm.messages[0]["role"], "system")
        self.assertEqual(llm.messages[1]["role"], "user")
        self.assertIn("JSON", llm.messages[0]["content"])
        self.assertIn("document-format-normalizer", llm.messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
