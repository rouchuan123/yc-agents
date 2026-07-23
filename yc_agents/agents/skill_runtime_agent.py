import json

from yc_agents.agents.skill_agent import SkillAgent
from yc_agents.core.llm_call import invoke_llm
from yc_agents.harness.context_manager import ContextManager
from yc_agents.harness.json_protocol import (
    InvalidModelJSONError,
    extract_model_json,
)
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
        memory_config=None,
        context_limit=8000,
        max_output_tokens=0,
        long_term_memory=None,
        session_id=None,
        rag_search_tool=None,
        rag_top_k=3,
        workspace_context=None,
        prompt_builder=None,
        intent_router=None,
        enabled_skills=None,
    ):
        self.llm = llm
        self.skills_dir = skills_dir
        self.enabled_skills = (
            None if enabled_skills is None else set(enabled_skills)
        )
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.skill_agent = SkillAgent(llm, prompt_builder=self.prompt_builder)
        self.context_manager = ContextManager()
        self.session_memory = session_memory or SessionMemory()
        self.summary_memory = summary_memory
        self.profile_memory = profile_memory
        self.memory_compressor = memory_compressor
        self.compression_threshold = compression_threshold
        self.memory_config = dict(memory_config or {})
        self.context_limit = int(context_limit or 8000)
        self.max_output_tokens = int(max_output_tokens or 0)
        self.long_term_memory = long_term_memory
        self.session_id = session_id
        self.rag_search_tool = rag_search_tool
        self.rag_top_k = rag_top_k
        self.workspace_context = workspace_context or {}
        self.intent_router = intent_router
        self.current_selected_skill_name = None
        self.current_selected_skill = None
        self.current_turn_is_plain_answer = True
        self.available_tools = list(
            self.workspace_context.get("available_tools") or []
        )

    def run(self, user_input):
        registry = self._load_registry()
        skills = self._discover_candidate_skills(registry, user_input)
        memory_context = self._load_memory_context(user_input, skills)

        selection_context = self.context_manager.build_skill_selection_context(
            user_input,
            skills,
            memory_context=memory_context,
            workspace_context=self.workspace_context,
        )
        selection_text = self.skill_agent.select_skill(selection_context)

        try:
            selection = self._parse_skill_selection(selection_text)
        except InvalidModelJSONError:
            return self._final_answer_json(selection_text)

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
        memory_context = self._load_memory_context(user_input, skills)

        selection_context = self.context_manager.build_skill_selection_context(
            user_input,
            skills,
            memory_context=memory_context,
            workspace_context=self.workspace_context,
        )
        selection_text = self.skill_agent.select_skill(selection_context)

        try:
            selection = self._parse_skill_selection(selection_text)
        except InvalidModelJSONError:
            yield self._final_answer_json(selection_text)
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

        for skill in SkillLoader(
            self.skills_dir,
            enabled_skills=self.enabled_skills,
        ).load_all():
            registry.register(skill)

        return registry

    def _plain_answer(self, user_input, memory_context=None):
        return self._think_protocol_json(
            self._build_plain_answer_messages(user_input, memory_context)
        )

    def _final_answer_json(self, content):
        return json.dumps(
            {"type": "final_answer", "content": str(content or "")},
            ensure_ascii=False,
        )

    def _stream_plain_answer(self, user_input, memory_context=None):
        yield from self._stream_protocol_json(
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
        self.current_selected_skill = None
        self.current_turn_is_plain_answer = True

    def _set_skill_tool_context(self, selected_skill):
        self.current_selected_skill_name = selected_skill.name
        self.current_selected_skill = selected_skill.to_dict()
        self.current_turn_is_plain_answer = False

    def current_turn_tool_context(self):
        return {
            "selected_skill": self.current_selected_skill_name,
            "available_tools": list(self.available_tools),
            "plain_answer": self.current_turn_is_plain_answer,
        }

    def current_turn_execution_context(self):
        return {
            "selected_skill": self.current_selected_skill,
            "available_tools": list(self.available_tools),
            "plain_answer": self.current_turn_is_plain_answer,
        }

    def _answer_with_skill(self, user_input, selected_skill, selection, memory_context=None):
        memory = memory_context or self.context_manager.build_memory_context()
        context = self.context_manager.build_skill_execution_context(
            user_input=user_input,
            selected_skill=selected_skill,
            selection=selection,
            memory_context=memory,
            rag_results=[],
            workspace_context=self.workspace_context,
        )
        messages = self.prompt_builder.skill_execution_messages(context)
        response = self._think_protocol_json(messages)

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
        memory = memory_context or self.context_manager.build_memory_context()
        context = self.context_manager.build_skill_execution_context(
            user_input=user_input,
            selected_skill=selected_skill,
            selection=selection,
            memory_context=memory,
            rag_results=[],
            workspace_context=self.workspace_context,
        )
        messages = self.prompt_builder.skill_execution_messages(context)

        yield from self._stream_protocol_json(messages)

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
            _preface, data = extract_model_json(
                response,
                allowed_types={"skill_selection"},
            )
        except InvalidModelJSONError:
            return False

        return data.get("type") == "skill_selection"

    def _retry_skill_execution(self, user_input, context):
        messages = self.prompt_builder.retry_skill_execution_messages(
            user_input=user_input,
            context=context,
        )
        return self._think_protocol_json(messages)

    def _load_memory_context(self, user_input="", skills=None):
        messages = self._load_memory_messages()
        summary = self._load_summary_memory()
        if self.memory_compressor is not None:
            additional = {
                "user_input": user_input,
                "workspace": self.workspace_context,
                "skills": [
                    self.context_manager._summarize_skill(skill)
                    for skill in (skills or [])
                ],
            }
            result = self.memory_compressor.compact_if_needed(
                messages,
                summary,
                active_max_tokens=int(
                    self.memory_config.get("activeContextMaxTokens", 64_000)
                ),
                context_limit=self.context_limit,
                trigger_percent=int(
                    self.memory_config.get("compactionTriggerPercent", 80)
                ),
                target_percent=int(
                    self.memory_config.get("compactionTargetPercent", 50)
                ),
                max_output_tokens=self.max_output_tokens,
                additional_tokens=len(json.dumps(additional, ensure_ascii=False)) // 4,
            )
            messages = result["messages"]
            summary = result["summary"]
            if result["compacted"]:
                self.session_memory.replace(messages)
        return self.context_manager.build_memory_context(
            memory_context={
                "session": messages,
                "summary": summary,
                "profile": self._load_profile_memory(),
                "retrieved": self._retrieve_long_term_memory(user_input),
            }
        )

    def _retrieve_long_term_memory(self, user_input):
        if self.long_term_memory is None or not str(user_input or "").strip():
            return []
        try:
            return self.long_term_memory.search(
                user_input,
                top_k=int(self.memory_config.get("retrieveTopK", 6)),
                token_budget=int(self.memory_config.get("retrievalTokenBudget", 4_000)),
                exclude_session_id=self.session_id,
            )
        except Exception:
            return []

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
        path = self.session_memory.save()
        self._persist_long_term_memory()
        return path

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
        path = self.session_memory.save()
        self._persist_long_term_memory()
        return path

    def _persist_long_term_memory(self):
        if self.long_term_memory is None or not self.session_id:
            return None
        summary = self._load_summary_memory()
        path = self.long_term_memory.write_session_log(
            self.session_id,
            self.session_memory.get_messages(),
            summary,
        )
        self.long_term_memory.maybe_dream(current_session_id=self.session_id)
        return path

    def run_with_observation(self, user_input, observation):
        memory = self._load_memory_context(user_input)
        messages = self.prompt_builder.observation_messages(
            user_input=user_input,
            memory=memory,
            workspace_context=self.workspace_context,
            observation=observation,
            execution_context=self.current_turn_execution_context(),
        )
        return self._think_protocol_json(messages)

    def run_with_protocol_error(
        self,
        user_input,
        error,
        expectation=None,
        execution_history=None,
        stage=None,
    ):
        allowed_types = set((expectation or {}).get("allowed_types") or ["tool_call", "final_answer"])
        raw_text = getattr(error, "raw_text", "")
        messages = self.prompt_builder.protocol_repair_messages(
            raw_text=raw_text,
            error_message=str(error),
            allowed_types=allowed_types,
            execution_context=self.current_turn_execution_context(),
            execution_history=execution_history or [],
            stage=stage,
        )
        return self._think_protocol_json(messages, usage_kind="auxiliary")

    def run_with_verification_feedback(
        self,
        user_input,
        response,
        verification,
        execution_history=None,
    ):
        messages = self.prompt_builder.verification_revision_messages(
            user_input=user_input,
            response=response,
            verification=verification,
            execution_context=self.current_turn_execution_context(),
            execution_history=execution_history or [],
            workspace_context=self.workspace_context,
        )
        return self._think_protocol_json(messages, usage_kind="auxiliary")

    def _think_protocol_json(self, messages, usage_kind="primary"):
        think_json = getattr(self.llm, "think_json", None)
        if callable(think_json):
            return invoke_llm(think_json, messages, usage_kind=usage_kind)
        return invoke_llm(self.llm.think, messages, usage_kind=usage_kind)

    def _stream_protocol_json(self, messages):
        stream_think_json = getattr(self.llm, "stream_think_json", None)
        if callable(stream_think_json):
            yield from stream_think_json(messages)
            return

        stream_think = getattr(self.llm, "stream_think", None)
        if callable(stream_think):
            yield from stream_think(messages)
            return

        yield self._think_protocol_json(messages)

    def _parse_skill_selection(self, text):
        _preface, selection = extract_model_json(
            text,
            allowed_types={"skill_selection"},
        )
        return selection
