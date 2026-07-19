import json

from yc_agents.harness.json_protocol import InvalidModelJSONError, parse_model_json
from yc_agents.core.llm_call import invoke_llm


class LLMIntentClassifier:
    def __init__(self, llm):
        self.llm = llm

    def classify(self, user_input, skills):
        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "llm_intent_classification",
                        "user_input": user_input,
                        "skills": [
                            self._summarize_skill(skill)
                            for skill in skills
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]
        think_json = getattr(self.llm, "think_json", None)
        raw_text = (
            invoke_llm(think_json, messages, usage_kind="auxiliary")
            if callable(think_json)
            else invoke_llm(self.llm.think, messages, usage_kind="auxiliary")
        )
        result = parse_model_json(raw_text, allowed_types={"skill_selection"})

        if result["type"] != "skill_selection":
            raise InvalidModelJSONError(
                "LLM intent classifier must return skill_selection JSON",
                raw_text=raw_text,
            )

        return result

    def _system_prompt(self):
        return (
            "你是 YCore 的 LLMIntentClassifier。"
            "你的任务是根据用户输入和 Skill 摘要列表，判断最可能使用哪个 Skill。"
            "你只输出合法 JSON，不要输出 Markdown 或解释。"
            "JSON 格式为："
            '{"type":"skill_selection","selected_skill":"skill-name-or-null","confidence":0.0,"reason":"选择理由"}'
        )

    def _summarize_skill(self, skill):
        return {
            "name": skill.name,
            "description": skill.description,
        }
