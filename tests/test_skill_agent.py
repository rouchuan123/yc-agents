import unittest

from yc_agents.agents.skill_agent import SkillAgent


class FakeLLM:
    def __init__(self):
        self.messages = None

    def think(self, messages):
        self.messages = messages
        return (
            '{"type":"skill_selection",'
            '"selected_skill":"opening-report",'
            '"confidence":0.9,'
            '"reason":"用户正在准备开题"}'
        )


class TestSkillAgent(unittest.TestCase):
    def test_select_skill_returns_model_json_text(self):
        llm = FakeLLM()
        agent = SkillAgent(llm)

        context = {
            "task": "skill_selection",
            "user_input": "帮我准备开题",
            "skills": [
                {
                    "name": "opening-report",
                    "description": "Help with opening report.",
                    "allowed_tools": ["rag_search"],
                }
            ],
        }

        result = agent.select_skill(context)

        self.assertIn('"type":"skill_selection"', result)
        self.assertIn('"selected_skill":"opening-report"', result)

    def test_select_skill_sends_context_to_llm(self):
        llm = FakeLLM()
        agent = SkillAgent(llm)

        context = {
            "task": "skill_selection",
            "user_input": "帮我准备开题",
            "skills": [
                {
                    "name": "opening-report",
                    "description": "Help with opening report.",
                    "allowed_tools": [],
                }
            ],
        }

        agent.select_skill(context)

        self.assertEqual(llm.messages[0]["role"], "system")
        self.assertEqual(llm.messages[1]["role"], "user")
        self.assertIn("只输出合法 JSON", llm.messages[0]["content"])
        self.assertIn("opening-report", llm.messages[1]["content"])


if __name__ == "__main__":
    unittest.main()