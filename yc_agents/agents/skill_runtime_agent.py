from yc_agents.agents.skill_agent import SkillAgent
from yc_agents.harness.context_manager import ContextManager
from yc_agents.harness.json_protocol import InvalidModelJSONError, parse_model_json
from yc_agents.memory.session import SessionMemory
from yc_agents.prompts.builder import PromptBuilder
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
        workspace_context=None,
        prompt_builder=None,
        intent_router=None,
    ):
        self.llm = llm
        self.skills_dir = skills_dir
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.skill_agent = SkillAgent(llm, prompt_builder=self.prompt_builder)
        self.context_manager = ContextManager()
        self.session_memory = session_memory or SessionMemory()
        self.summary_memory = summary_memory
        self.profile_memory = profile_memory
        self.memory_compressor = memory_compressor
        self.compression_threshold = compression_threshold
        self.rag_search_tool = rag_search_tool
        self.rag_top_k = rag_top_k
        self.workspace_context = workspace_context or {}
        self.intent_router = intent_router
        self.current_selected_skill_name = None
        self.current_skill_allowed_tools = []
        self.current_turn_is_plain_answer = True
        self.plain_answer_allowed_tools = ["workspace_files", "file_reader"]

    def run(self, user_input):
        registry = self._load_registry()
        skills = self._discover_candidate_skills(registry, user_input)
        memory_context = self._load_memory_context()

        selection_context = self.context_manager.build_skill_selection_context(
            user_input,
            skills,
            memory_context=memory_context,
            workspace_context=self.workspace_context,
        )
        selection_text = self.skill_agent.select_skill(selection_context)

        try:
            selection = parse_model_json(selection_text)
        except InvalidModelJSONError:
            return selection_text

        selected_name = selection.get("selected_skill")

        if not selected_name:
            self._set_plain_tool_context()
            return self._plain_answer(user_input, memory_context)

        try:
            selected_skill = registry.get_skill(selected_name)
        except KeyError:
            self._set_plain_tool_context()
            return self._plain_answer(user_input, memory_context)

        self._set_skill_tool_context(selected_skill)
        return self._answer_with_skill(user_input, selected_skill, selection, memory_context)

    def stream(self, user_input):
        registry = self._load_registry()
        skills = self._discover_candidate_skills(registry, user_input)
        memory_context = self._load_memory_context()

        selection_context = self.context_manager.build_skill_selection_context(
            user_input,
            skills,
            memory_context=memory_context,
            workspace_context=self.workspace_context,
        )
        selection_text = self.skill_agent.select_skill(selection_context)

        try:
            selection = parse_model_json(selection_text)
        except InvalidModelJSONError:
            yield selection_text
            return

        selected_name = selection.get("selected_skill")

        if not selected_name:
            self._set_plain_tool_context()
            yield from self._stream_plain_answer(user_input, memory_context)
            return

        try:
            selected_skill = registry.get_skill(selected_name)
        except KeyError:
            self._set_plain_tool_context()
            yield from self._stream_plain_answer(user_input, memory_context)
            return

        self._set_skill_tool_context(selected_skill)
        yield from self._stream_answer_with_skill(
            user_input,
            selected_skill,
            selection,
            memory_context,
        )

    def _load_registry(self):
        registry = SkillRegistry()

        for skill in SkillLoader(self.skills_dir).load_all():
            registry.register(skill)

        return registry

    def _plain_answer(self, user_input, memory_context=None):
        return self.llm.think(
            self._build_plain_answer_messages(user_input, memory_context)
        )

    def _stream_plain_answer(self, user_input, memory_context=None):
        stream_think = getattr(self.llm, "stream_think", None)

        if not callable(stream_think):
            yield self._plain_answer(user_input, memory_context)
            return

        yield from stream_think(
            self._build_plain_answer_messages(user_input, memory_context)
        )

    def _build_plain_answer_messages(self, user_input, memory_context=None):
        memory = memory_context or self.context_manager.build_memory_context()
        return self.prompt_builder.plain_answer_messages(
            user_input=user_input,
            memory=memory,
            workspace_context=self.workspace_context,
        )

    def _set_plain_tool_context(self):
        self.current_selected_skill_name = None
        self.current_skill_allowed_tools = list(self.plain_answer_allowed_tools)
        self.current_turn_is_plain_answer = True

    def _set_skill_tool_context(self, selected_skill):
        self.current_selected_skill_name = selected_skill.name
        self.current_skill_allowed_tools = list(selected_skill.allowed_tools)
        self.current_turn_is_plain_answer = False

    def current_turn_tool_context(self):
        return {
            "selected_skill": self.current_selected_skill_name,
            "allowed_tools": list(self.current_skill_allowed_tools),
            "plain_answer": self.current_turn_is_plain_answer,
        }

    def _answer_with_skill(self, user_input, selected_skill, selection, memory_context=None):
        memory = memory_context or self.context_manager.build_memory_context()
        rag_results = self._load_rag_results(user_input, selected_skill)
        context = self.context_manager.build_skill_execution_context(
            user_input=user_input,
            selected_skill=selected_skill,
            selection=selection,
            memory_context=memory,
            rag_results=rag_results,
            workspace_context=self.workspace_context,
        )
        messages = self.prompt_builder.skill_execution_messages(context)
        response = self.llm.think(messages)

        if self._is_repeated_skill_selection(response):
            return self._retry_skill_execution(user_input, context)

        return response

    def _stream_answer_with_skill(
        self,
        user_input,
        selected_skill,
        selection,
        memory_context=None,
    ):
        stream_think = getattr(self.llm, "stream_think", None)

        if not callable(stream_think):
            yield self._answer_with_skill(user_input, selected_skill, selection, memory_context)
            return

        memory = memory_context or self.context_manager.build_memory_context()
        rag_results = self._load_rag_results(user_input, selected_skill)
        context = self.context_manager.build_skill_execution_context(
            user_input=user_input,
            selected_skill=selected_skill,
            selection=selection,
            memory_context=memory,
            rag_results=rag_results,
            workspace_context=self.workspace_context,
        )
        messages = self.prompt_builder.skill_execution_messages(context)

        yield from stream_think(messages)

    def _discover_candidate_skills(self, registry, user_input):
        skills = list(registry.skills.values())

        if self.intent_router is not None:
            route = self.intent_router.route(user_input, skills)
            ordered_names = [
                item["skill_name"]
                for item in route.get("candidates", [])
                if item.get("skill_name") in registry.skills
            ]
            ordered = [registry.skills[name] for name in ordered_names]
            if ordered:
                return ordered[:5]

        discovered = registry.discover(user_input, top_k=5)
        if not discovered:
            return skills

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
        messages = self.prompt_builder.retry_skill_execution_messages(
            user_input=user_input,
            context=context,
        )
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

    def remember_structured_turn(self, user_input, response, process_entries=None):
        self.session_memory.load()
        self.session_memory.add_message("user", user_input)
        add_structured_message = getattr(self.session_memory, "add_structured_message", None)
        if callable(add_structured_message):
            add_structured_message(
                "assistant",
                response,
                process_entries=list(process_entries or []),
            )
        else:
            self.session_memory.add_message("assistant", response)
        return self.session_memory.save()

    def run_with_observation(self, user_input, observation):
        memory = self._load_memory_context()
        messages = self.prompt_builder.observation_messages(
            user_input=user_input,
            memory=memory,
            workspace_context=self.workspace_context,
            observation=observation,
        )
        return self.llm.think(messages)

    def _load_rag_results(self, user_input, selected_skill):
        if self.rag_search_tool is None:
            return []

        if "rag_search" not in selected_skill.allowed_tools:
            return []

        return self.rag_search_tool.run(user_input, top_k=self.rag_top_k)
