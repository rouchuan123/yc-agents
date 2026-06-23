import json

from yc_agents.agents.skill_agent import SkillAgent
from yc_agents.harness.context_manager import ContextManager
from yc_agents.harness.json_protocol import InvalidModelJSONError, parse_model_json
from yc_agents.memory.session import SessionMemory
from yc_agents.skills.loader import SkillLoader
from yc_agents.skills.registry import SkillRegistry


class SkillRuntimeAgent:
    def __init__(
        self,
        llm,
        skills_dir="skills",
        session_memory=None,
        summary_memory=None,
        profile_memory=None,
        memory_compressor=None,
        compression_threshold=None,
        rag_search_tool=None,
        rag_top_k=3,
    ):
        self.llm = llm
        self.skills_dir = skills_dir
        self.skill_agent = SkillAgent(llm)
        self.context_manager = ContextManager()
        self.session_memory = session_memory or SessionMemory()
        self.summary_memory = summary_memory
        self.profile_memory = profile_memory
        self.memory_compressor = memory_compressor
        self.compression_threshold = compression_threshold
        self.rag_search_tool = rag_search_tool
        self.rag_top_k = rag_top_k

    def run(self, user_input):
        registry = self._load_registry()
        skills = self._discover_candidate_skills(registry, user_input)
        memory_context = self._load_memory_context()
        memory_messages = memory_context["session"]

        selection_context = self.context_manager.build_skill_selection_context(
            user_input,
            skills,
            memory_context=memory_context,
        )
        selection_text = self.skill_agent.select_skill(selection_context)

        try:
            selection = parse_model_json(selection_text)
        except InvalidModelJSONError:
            return selection_text

        selected_name = selection.get("selected_skill")

        if not selected_name:
            return self._plain_answer(user_input, memory_context)

        try:
            selected_skill = registry.get_skill(selected_name)
        except KeyError:
            return self._plain_answer(user_input, memory_context)

        return self._answer_with_skill(user_input, selected_skill, selection, memory_context)

    def _load_registry(self):
        registry = SkillRegistry()

        for skill in SkillLoader(self.skills_dir).load_all():
            registry.register(skill)

        return registry

    def _plain_answer(self, user_input, memory_context=None):
        memory = memory_context or self.context_manager.build_memory_context()
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
                        "memory": memory,
                        "recent_messages": memory["session"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]
        return self.llm.think(messages)

    def _answer_with_skill(self, user_input, selected_skill, selection, memory_context=None):
        memory = memory_context or self.context_manager.build_memory_context()
        rag_results = self._load_rag_results(user_input, selected_skill)
        context = self.context_manager.build_skill_execution_context(
            user_input=user_input,
            selected_skill=selected_skill,
            selection=selection,
            memory_context=memory,
            rag_results=rag_results,
        )
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
                    context,
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

        response = self.llm.think(messages)

        if self._is_repeated_skill_selection(response):
            return self._retry_skill_execution(user_input, context)

        return response

    def _discover_candidate_skills(self, registry, user_input):
        discovered = registry.discover(user_input, top_k=5)
        if not discovered:
            return list(registry.skills.values())

        return [result.skill for result in discovered]

    def _load_memory_messages(self):
        return self.session_memory.load()

    def _is_repeated_skill_selection(self, response):
        try:
            data = parse_model_json(response)
        except InvalidModelJSONError:
            return False

        return data.get("type") == "skill_selection"

    def _retry_skill_execution(self, user_input, context):
        messages = [
            {
                "role": "system",
                "content": (
                    "你已经完成 Skill 选择，现在必须执行 selected_skill。"
                    "不要再输出 skill_selection JSON。"
                    "如果用户没有要求保存文件，就直接用自然语言回答用户。"
                    "如果用户明确要求保存文件，只输出 tool_call JSON。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_input": user_input,
                        "execution_context": context,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

        return self.llm.think(messages)

    def _load_memory_context(self):
        return self.context_manager.build_memory_context(
            session=self._load_memory_messages(),
            summary=self._load_summary_memory(),
            profile=self._load_profile_memory(),
            memory_compressor=self.memory_compressor,
            compression_threshold=self.compression_threshold,
        )

    def _load_summary_memory(self):
        if self.summary_memory is None:
            return ""

        return self.summary_memory.load()

    def _load_profile_memory(self):
        if self.profile_memory is None:
            return {}

        return self.profile_memory.load()

    def remember_turn(self, user_input, response):
        self.session_memory.load()
        self.session_memory.add_message("user", user_input)
        self.session_memory.add_message("assistant", response)
        return self.session_memory.save()

    def run_with_observation(self, user_input, observation):
        memory = self._load_memory_context()
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
                        "memory": memory,
                        "recent_messages": memory["session"],
                        "observation": observation,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

        return self.llm.think(messages)

    def _load_rag_results(self, user_input, selected_skill):
        if self.rag_search_tool is None:
            return []

        if "rag_search" not in selected_skill.allowed_tools:
            return []

        return self.rag_search_tool.run(user_input, top_k=self.rag_top_k)
