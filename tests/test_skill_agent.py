import unittest

from yc_agents.agents.skill_agent import SkillAgent


class FakeLLM:
    def __init__(self):
        self.messages = None

    def think(self, messages):
        self.messages = messages
        return (
            '{"type":"skill_selection",'
            '"selected_skill":"code-review",'
            '"confidence":0.9,'
            '"reason":"The user asked for a project review"}'
        )


class TestSkillAgent(unittest.TestCase):
    def test_select_skill_returns_model_json_text(self):
        llm = FakeLLM()
        agent = SkillAgent(llm)

        context = {
            "task": "skill_selection",
            "user_input": "review this project",
            "skills": [
                {
                    "name": "code-review",
                    "description": "Summarize project architecture and risks",
                    "allowed_tools": ["workspace_files", "file_reader"],
                }
            ],
        }

        result = agent.select_skill(context)

        self.assertIn('"type":"skill_selection"', result)
        self.assertIn('"selected_skill":"code-review"', result)

    def test_select_skill_sends_context_to_llm(self):
        llm = FakeLLM()
        agent = SkillAgent(llm)

        context = {
            "task": "skill_selection",
            "user_input": "review this project",
            "skills": [
                {
                    "name": "code-review",
                    "description": "Summarize project architecture and risks",
                    "allowed_tools": [],
                }
            ],
        }

        agent.select_skill(context)

        self.assertEqual(llm.messages[0]["role"], "system")
        self.assertEqual(llm.messages[1]["role"], "user")
        self.assertIn("Skill selection protocol", llm.messages[0]["content"])
        self.assertIn("code-review", llm.messages[1]["content"])
        self.assertNotIn("Word", llm.messages[0]["content"])
        self.assertNotIn("docx_format_normalizer", llm.messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
