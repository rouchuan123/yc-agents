import unittest

from yc_agents.harness.orchestrator import MultiAgentOrchestrator


class FakeManagerAgent:
    def __init__(self, target_agent):
        self.target_agent = target_agent

    def route(self, user_input):
        return {
            "type": "agent_route",
            "target_agent": self.target_agent,
            "confidence": 0.9,
            "reason": "test route",
        }


class FakeAgent:
    def __init__(self, name):
        self.name = name
        self.inputs = []

    def run(self, user_input):
        self.inputs.append(user_input)
        return f"{self.name}: {user_input}"


class TestMultiAgentOrchestrator(unittest.TestCase):
    def test_routes_to_selected_agent(self):
        skill_agent = FakeAgent("skill")
        simple_agent = FakeAgent("simple")
        orchestrator = MultiAgentOrchestrator(
            manager_agent=FakeManagerAgent("skill_agent"),
            agents={
                "skill_agent": skill_agent,
                "simple_agent": simple_agent,
            },
        )

        result = orchestrator.run("帮我准备开题")

        self.assertEqual(result["type"], "orchestrator_result")
        self.assertEqual(result["route"]["target_agent"], "skill_agent")
        self.assertEqual(result["content"], "skill: 帮我准备开题")
        self.assertEqual(skill_agent.inputs, ["帮我准备开题"])
        self.assertEqual(simple_agent.inputs, [])

    def test_unknown_agent_returns_error_result(self):
        orchestrator = MultiAgentOrchestrator(
            manager_agent=FakeManagerAgent("missing_agent"),
            agents={},
        )

        result = orchestrator.run("hello")

        self.assertEqual(result["type"], "orchestrator_error")
        self.assertEqual(result["target_agent"], "missing_agent")


if __name__ == "__main__":
    unittest.main()
