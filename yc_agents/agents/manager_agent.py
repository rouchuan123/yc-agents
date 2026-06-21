SKILL_TASK_KEYWORDS = {
    "开题",
    "论文",
    "文献",
    "综述",
    "系统设计",
    "skill",
    "proposal",
    "literature",
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
                "reason": f"任务关键词命中：{', '.join(matched_keywords)}",
            }

        return {
            "type": "agent_route",
            "target_agent": "simple_agent",
            "confidence": 0.5,
            "reason": "未命中专业任务关键词，走基础对话 Agent",
        }
