import json


class SkillAgent:
    def __init__(self, llm):
        self.llm = llm

    def select_skill(self, context):
        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, indent=2),
            },
        ]

        return self.llm.think(messages)

    def _system_prompt(self):
        return (
            "你是 YCore 的 SkillAgent。"
            "你的任务是根据用户输入和 skills 列表选择最合适的 Skill。"
            "你必须只输出合法 JSON，不要输出 Markdown，不要解释。"
            "JSON 格式为："
            '{"type":"skill_selection","selected_skill":"skill-name-or-null","confidence":0.0,"reason":"选择理由"}'
        )
