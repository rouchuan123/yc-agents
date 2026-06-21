class MultiAgentOrchestrator:
    def __init__(self, manager_agent, agents):
        self.manager_agent = manager_agent
        self.agents = agents

    def run(self, user_input):
        route = self.manager_agent.route(user_input)
        target_agent = route.get("target_agent")
        agent = self.agents.get(target_agent)

        if agent is None:
            return {
                "type": "orchestrator_error",
                "target_agent": target_agent,
                "route": route,
                "error": f"Target agent is not registered: {target_agent}",
            }

        return {
            "type": "orchestrator_result",
            "target_agent": target_agent,
            "route": route,
            "content": agent.run(user_input),
        }
