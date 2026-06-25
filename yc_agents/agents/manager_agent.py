SKILL_TASK_KEYWORDS = {
    "skill",
    "review",
    "architecture",
    "evaluate",
    "summary",
    "project",
    "proposal",
}


class ManagerAgent:
    def __init__(self, skill_task_keywords=None):
        self.skill_task_keywords = set(skill_task_keywords or SKILL_TASK_KEYWORDS)

    def route(self, user_input):
        text = (user_input or "").lower()
        matched_keywords = [
            keyword
            for keyword in self.skill_task_keywords
            if keyword.lower() in text
        ]

        if matched_keywords:
            return {
                "type": "agent_route",
                "target_agent": "skill_agent",
                "confidence": min(1.0, len(matched_keywords) / 3),
                "reason": f"Task keywords matched: {', '.join(matched_keywords)}",
            }

        return {
            "type": "agent_route",
            "target_agent": "simple_agent",
            "confidence": 0.5,
            "reason": "No specialist task keywords matched; using simple agent",
        }
