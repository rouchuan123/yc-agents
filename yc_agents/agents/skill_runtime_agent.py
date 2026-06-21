import json

from yc_agents.agents.skill_agent import SkillAgent
from yc_agents.harness.context_manager import ContextManager
from yc_agents.harness.json_protocol import InvalidModelJSONError, parse_model_json
from yc_agents.memory.session import SessionMemory
from yc_agents.skills.loader import SkillLoader
from yc_agents.skills.registry import SkillRegistry


class SkillRuntimeAgent:
    def __init__(self, llm, skills_dir="skills", session_memory=None):
        self.llm = llm
        self.skills_dir = skills_dir
        self.skill_agent = SkillAgent(llm)
        self.context_manager = ContextManager()
        self.session_memory = session_memory or SessionMemory()

    def run(self, user_input):
        registry = self._load_registry()
        skills = list(registry.skills.values())
        memory_messages = self._load_memory_messages()

        selection_context = self.context_manager.build_skill_selection_context(
            user_input,
            skills,
            memory_messages=memory_messages,
        )
        selection_text = self.skill_agent.select_skill(selection_context)

        try:
            selection = parse_model_json(selection_text)
        except InvalidModelJSONError:
            return selection_text

        selected_name = selection.get("selected_skill")

        if not selected_name:
            return self._plain_answer(user_input, memory_messages)

        try:
            selected_skill = registry.get_skill(selected_name)
        except KeyError:
            return self._plain_answer(user_input, memory_messages)

        return self._answer_with_skill(user_input, selected_skill, selection, memory_messages)

    def _load_registry(self):
        registry = SkillRegistry()

        for skill in SkillLoader(self.skills_dir).load_all():
            registry.register(skill)

        return registry

    def _plain_answer(self, user_input, memory_messages=None):
        messages = [
            {
                "role": "system",
                "content": "你是一个耐心的小白编程老师和论文助手。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_input": user_input,
                        "recent_messages": memory_messages or [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]
        return self.llm.think(messages)

    def _answer_with_skill(self, user_input, selected_skill, selection, memory_messages=None):
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 yc-agents 的 Skill-driven Agent。"
                    "你必须根据给定 Skill 的操作说明来回答用户。"
                    "不要编造资料、文献、导师意见或文件路径。"
                    "如果用户明确要求保存、导出或生成 Markdown 文件，"
                    "你必须只输出合法 tool_call JSON，不要输出 Markdown 或解释。"
                    "tool_call 格式为："
                    '{"type":"tool_call","tool_name":"markdown_writer",'
                    '"arguments":{"file_name":"draft.md","content":"# Draft"},'
                    '"reason":"保存 Markdown 草稿"}'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_input": user_input,
                        "recent_messages": memory_messages or [],
                        "selected_skill": selected_skill.to_dict(),
                        "selection": selection,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

        return self.llm.think(messages)

    def _load_memory_messages(self):
        return self.session_memory.load()

    def remember_turn(self, user_input, response):
        self.session_memory.load()
        self.session_memory.add_message("user", user_input)
        self.session_memory.add_message("assistant", response)
        return self.session_memory.save()

    def run_with_observation(self, user_input, observation):
        memory_messages = self._load_memory_messages()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the yc-agents Skill-driven Agent. "
                    "You have received one tool execution observation. "
                    "Return only valid final_answer JSON. "
                    "Do not return Markdown or extra explanation. "
                    'Format: {"type":"final_answer","content":"final answer for the user"}'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_input": user_input,
                        "recent_messages": memory_messages,
                        "observation": observation,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

        return self.llm.think(messages)
