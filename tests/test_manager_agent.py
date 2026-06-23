import unittest

from yc_agents.agents.manager_agent import ManagerAgent


class TestManagerAgent(unittest.TestCase):
    def test_routes_skill_tasks_to_skill_agent(self):
        manager = ManagerAgent()

        decision = manager.route("帮我准备开题报告")

        self.assertEqual(decision["type"], "agent_route")
        self.assertEqual(decision["target_agent"], "skill_agent")
        self.assertGreater(decision["confidence"], 0)

    def test_routes_general_chat_to_simple_agent(self):
        manager = ManagerAgent()

        decision = manager.route("你好，今天聊两句")

        self.assertEqual(decision["target_agent"], "simple_agent")


if __name__ == "__main__":
    unittest.main()
