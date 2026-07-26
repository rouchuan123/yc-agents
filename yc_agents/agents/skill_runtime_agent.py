import inspect
import json

from yc_agents.agents.skill_agent import SkillAgent
from yc_agents.core.llm_call import invoke_llm
from yc_agents.harness.context_manager import ContextManager
from yc_agents.harness.json_protocol import (
    InvalidModelJSONError,
    extract_model_json,
)
from yc_agents.harness.process_events import summarize_tool_result
from yc_agents.memory.compressor import estimate_tokens
from yc_agents.memory.session import SessionMemory
from yc_agents.prompts.builder import PromptBuilder
from yc_agents.skills.loader import SkillLoader
from yc_agents.skills.registry import SkillRegistry


CONTINUATION_CUES = (
    "继续",
    "接着",
    "然后",
    "顺便",
    "还有",
    "下一步",
    "再来",
    "continue",
    "go on",
    "next",
    "keep going",
    "then",
    "also",
)


class SkillRuntimeAgent:
    def __init__(
        self,
        llm,
        skills_dir="skills",
        session_memory=None,
        summary_memory=None,
        profile_memory=None,
        memory_compressor=None,
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
        tool_calling="json-protocol",
        native_tools=None,
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
        self.current_skill_context = None
        self.current_turn_is_plain_answer = True
        self.available_tools = list(
            self.workspace_context.get("available_tools") or []
        )
        self._turn_memory_context = None
        # 原生 function calling：tool_calling='native' 且 native_tools 非空时，
        # 轮内模型调用带 OpenAI tools 数组、消费结构化 tool_calls；否则维持
        # json-protocol 文本协议。降级标记只影响单轮。
        self.tool_calling = str(tool_calling or "json-protocol")
        self.native_tools = list(native_tools or [])
        self._turn_native_disabled = False
        self._native_fallback_pending = False
        # 轮级追加式消息状态：head 是轮开始时冻结的稳定前缀，steps 是
        # 只增不改的工具交换对；summary 槽位承接被折叠的最老交换对。
        self._turn_head = None
        self._turn_steps = []
        self._turn_summary_entries = []
        self._turn_summary_message = None
        self._turn_last_response = None
        self._turn_pending_entry = None

    def run(self, user_input):
        self._reset_turn_state()
        registry = self._load_registry()

        sticky_skill = self._sticky_skill(user_input, registry)
        if sticky_skill is not None:
            memory_context = self._begin_turn_memory(user_input, [sticky_skill])
            self._set_skill_tool_context(sticky_skill)
            return self._answer_with_skill(
                user_input,
                sticky_skill,
                self._sticky_selection(sticky_skill),
                memory_context,
            )

        skills = self._discover_candidate_skills(registry, user_input)
        memory_context = self._begin_turn_memory(user_input, skills)

        selection_context = self.context_manager.build_skill_selection_context(
            user_input,
            skills,
            memory_context=memory_context,
            workspace_context=self.workspace_context,
        )
        selection_text = self.skill_agent.select_skill(selection_context)

        try:
            selection = self._parse_skill_selection(selection_text)
        except InvalidModelJSONError as error:
            selection = self._repair_skill_selection(selection_text, error)

        selected_name = (selection or {}).get("selected_skill")

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
        self._reset_turn_state()
        registry = self._load_registry()

        sticky_skill = self._sticky_skill(user_input, registry)
        if sticky_skill is not None:
            memory_context = self._begin_turn_memory(user_input, [sticky_skill])
            self._set_skill_tool_context(sticky_skill)
            yield from self._stream_answer_with_skill(
                user_input,
                sticky_skill,
                self._sticky_selection(sticky_skill),
                memory_context,
            )
            return

        skills = self._discover_candidate_skills(registry, user_input)
        memory_context = self._begin_turn_memory(user_input, skills)

        selection_context = self.context_manager.build_skill_selection_context(
            user_input,
            skills,
            memory_context=memory_context,
            workspace_context=self.workspace_context,
        )
        selection_text = self.skill_agent.select_skill(selection_context)

        try:
            selection = self._parse_skill_selection(selection_text)
        except InvalidModelJSONError as error:
            selection = self._repair_skill_selection(selection_text, error)

        selected_name = (selection or {}).get("selected_skill")

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
        messages = self._build_plain_answer_messages(
            user_input,
            memory_context,
            native_tools=self.native_turn_active(),
        )
        self._begin_turn_messages(messages)
        response = self._think_turn(messages)
        self._turn_last_response = response
        return response

    def _repair_skill_selection(self, raw_text, error):
        # One repair call fixes the JSON shape only; if that also fails the
        # turn degrades to a plain answer instead of leaking the raw
        # selection text to the user.
        messages = self.prompt_builder.protocol_repair_messages(
            raw_text=raw_text,
            error_message=str(error),
            allowed_types={"skill_selection"},
            stage="skill_selection",
        )
        try:
            repaired = self._think_protocol_json(messages, usage_kind="auxiliary")
            return self._parse_skill_selection(repaired)
        except Exception:
            return None

    def _sticky_skill(self, user_input, registry):
        previous_name = self.current_selected_skill_name
        if not previous_name or previous_name not in registry.skills:
            return None

        previous = registry.skills[previous_name]
        others = [
            skill
            for skill in registry.skills.values()
            if skill.name != previous_name
        ]
        if self._mentions_skill(user_input, others):
            return None

        if self._mentions_skill(user_input, [previous]):
            return previous

        text = str(user_input or "").strip()
        if len(text) < 40 and self._looks_like_continuation(text):
            return previous

        return None

    def _mentions_skill(self, user_input, skills):
        text = str(user_input or "").lower()
        for skill in skills:
            keywords = [skill.name] + list(getattr(skill, "triggers", []) or [])
            for keyword in keywords:
                keyword = str(keyword or "").strip().lower()
                if keyword and keyword in text:
                    return True
        return False

    def _looks_like_continuation(self, text):
        lowered = text.lower()
        return any(cue in lowered for cue in CONTINUATION_CUES)

    def _sticky_selection(self, skill):
        return {
            "type": "skill_selection",
            "selected_skill": skill.name,
            "confidence": 0.9,
            "reason": "Continuing the skill selected in the previous turn.",
            "sticky": True,
        }

    def _stream_plain_answer(self, user_input, memory_context=None):
        messages = self._build_plain_answer_messages(user_input, memory_context)
        self._begin_turn_messages(messages)
        yield from self._stream_protocol_json_tracked(messages)

    def _build_plain_answer_messages(
        self, user_input, memory_context=None, native_tools=False
    ):
        memory = memory_context or self.context_manager.build_memory_context()
        return self.prompt_builder.plain_answer_messages(
            user_input=user_input,
            memory=memory,
            workspace_context=self.workspace_context,
            native_tools=native_tools,
        )

    def _set_plain_tool_context(self):
        self.current_selected_skill_name = None
        self.current_selected_skill = None
        self.current_skill_context = None
        self.current_turn_is_plain_answer = True

    def _set_skill_tool_context(self, selected_skill):
        self.current_selected_skill_name = selected_skill.name
        self.current_selected_skill = selected_skill.to_dict()
        self.current_skill_context = self._compact_skill_context(selected_skill)
        self.current_turn_is_plain_answer = False

    def _compact_skill_context(self, selected_skill):
        # Observation and revision steps only need to know which skill is
        # active; the full body already went out in the first execution
        # message of the turn.
        to_context_dict = getattr(selected_skill, "to_context_dict", None)
        if callable(to_context_dict):
            return to_context_dict()

        return {
            "name": selected_skill.name,
            "allowed_tools": list(getattr(selected_skill, "allowed_tools", []) or []),
            "stage_hint": (
                "The full skill instructions were provided in the first execution message "
                "of this turn; keep following that workflow."
            ),
        }

    def current_turn_tool_context(self):
        return {
            "selected_skill": self.current_selected_skill_name,
            "available_tools": list(self.available_tools),
            "plain_answer": self.current_turn_is_plain_answer,
        }

    def current_turn_execution_context(self):
        return {
            "selected_skill": self.current_skill_context,
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
        messages = self.prompt_builder.skill_execution_messages(
            context,
            native_tools=self.native_turn_active(),
        )
        self._begin_turn_messages(messages)
        response = self._think_turn(messages)
        self._turn_last_response = response

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
        self._begin_turn_messages(messages)

        yield from self._stream_protocol_json_tracked(messages)

    def _discover_candidate_skills(self, registry, user_input):
        skills = list(registry.skills.values())

        if self.intent_router is not None:
            route = self._route_intent(user_input, skills)
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

    def _route_intent(self, user_input, skills):
        # Routers that understand allow_llm_skip may short-circuit the LLM
        # vote; older or fake routers without the parameter keep working.
        route_method = self.intent_router.route
        try:
            supports_skip = "allow_llm_skip" in inspect.signature(route_method).parameters
        except (TypeError, ValueError):
            supports_skip = False

        if supports_skip:
            return route_method(user_input, skills, allow_llm_skip=True)
        return route_method(user_input, skills)

    def _load_memory_messages(self):
        return self.session_memory.load()

    def _is_repeated_skill_selection(self, response):
        if not isinstance(response, str):
            # 原生 FC 返回 ModelTurn：带 tool_calls 的回合必然不是技能选择，
            # 纯 content 回合退回文本判定。
            if getattr(response, "tool_calls", None):
                return False
            response = str(getattr(response, "content", "") or "")
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
            native_tools=self.native_turn_active(),
        )
        # 重试消息取代原执行消息成为本轮的稳定前缀：后续观察步在它
        # 之上追加，而不是回到已被模型误答的第一版前缀。
        self._begin_turn_messages(messages)
        response = self._think_turn(messages)
        self._turn_last_response = response
        return response

    def _begin_turn_memory(self, user_input, skills):
        # Assemble the memory context once per turn; observation steps reuse
        # this cache instead of re-reading disk and re-running retrieval for
        # every tool call.
        self._turn_memory_context = self._load_memory_context(user_input, skills)
        return self._turn_memory_context

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
                additional_tokens=estimate_tokens(additional),
            )
            messages = result["messages"]
            summary = result["summary"]
            if result["compacted"]:
                self.session_memory.replace(messages)
        return self.context_manager.build_memory_context(
            memory_context={
                "session": self._dialogue_messages(messages),
                "summary": summary,
                "profile": self._load_profile_memory(),
                "retrieved": self._retrieve_long_term_memory(user_input),
            }
        )

    @staticmethod
    def _dialogue_messages(messages):
        # Session files keep process_entries and other tool traces for the
        # TUI; prompts only need the dialogue itself.
        cleaned = []
        for message in messages or []:
            if isinstance(message, dict):
                cleaned.append(
                    {key: message[key] for key in ("role", "content") if key in message}
                )
            else:
                cleaned.append(message)
        return cleaned

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
        self._turn_memory_context = None
        self._reset_turn_state()
        self.session_memory.load()
        self.session_memory.add_message("user", user_input)
        self.session_memory.add_message("assistant", response)
        path = self.session_memory.save()
        self._persist_long_term_memory()
        return path

    def remember_structured_turn(self, user_input, response, process_entries=None):
        self._turn_memory_context = None
        self._reset_turn_state()
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

    # ------------------------------------------------------------------
    # 轮级追加式消息：轮开始冻结 [system, user] 前缀，之后每个工具步只
    # 追加 assistant/user 两条消息，让 provider 的前缀缓存持续命中。
    # ------------------------------------------------------------------

    def turn_messages_active(self):
        return self._turn_head is not None

    def native_tools_enabled(self):
        return self.tool_calling == "native" and bool(self.native_tools)

    def native_turn_active(self):
        return self.native_tools_enabled() and not self._turn_native_disabled

    def disable_native_for_turn(self):
        """provider 对 tools 参数报错时由运行时调用：下一次 run() 重建的这
        一轮整体降级 json-protocol，再往后的新轮次重新尝试原生 FC。"""
        self._native_fallback_pending = True
        self._turn_native_disabled = True

    def _reset_turn_state(self):
        self._turn_head = None
        self._turn_steps = []
        self._turn_summary_entries = []
        self._turn_summary_message = None
        self._turn_last_response = None
        self._turn_pending_entry = None
        # 降级标记只作用于紧接着重建的这一轮，消费后自动清除。
        self._turn_native_disabled = self._native_fallback_pending
        self._native_fallback_pending = False

    def _think_turn(self, messages, usage_kind="primary"):
        # 原生 FC 轮：把 OpenAI tools 数组透传给 think，拿回结构化 ModelTurn；
        # 其余场景维持 json-protocol 文本协议，返回 str。
        if self.native_turn_active():
            return invoke_llm(
                self.llm.think,
                messages,
                usage_kind=usage_kind,
                tools=list(self.native_tools),
            )
        return self._think_protocol_json(messages, usage_kind)

    def _begin_turn_messages(self, head_messages):
        self._turn_head = list(head_messages)
        self._turn_steps = []
        self._turn_summary_entries = []
        self._turn_summary_message = None
        self._turn_last_response = None
        self._turn_pending_entry = None

    def _current_turn_messages(self):
        messages = list(self._turn_head)
        if self._turn_summary_message is not None:
            messages.append(self._turn_summary_message)
        for step in self._turn_steps:
            messages.extend(step["messages"])
        return messages

    def _fold_turn_messages_if_needed(self):
        # 单调折叠：消息估算超过 context_limit//2 时，把最老的一半交换
        # 对压成一条紧凑 summary 消息。只折叠、不回滚，折叠完成后的新
        # 前缀重新保持逐字节稳定。
        limit = max(1, self.context_limit // 2)
        if estimate_tokens(self._current_turn_messages()) <= limit:
            return False
        if len(self._turn_steps) < 2:
            return False
        fold_count = len(self._turn_steps) // 2
        folded = self._turn_steps[:fold_count]
        self._turn_steps = self._turn_steps[fold_count:]
        self._turn_summary_entries.extend(
            self._compact_turn_entry(entry)
            for step in folded
            for entry in step["entries"]
        )
        self._turn_summary_message = self.prompt_builder.folded_history_message(
            list(self._turn_summary_entries)
        )
        return True

    def _compact_turn_entry(self, entry):
        tool_call = dict(entry.get("tool_call") or {})
        tool_result = entry.get("tool_result")
        tool_name = str(tool_call.get("tool_name") or "tool")
        compact = {
            "tool_name": tool_name,
            "arguments": dict(tool_call.get("arguments") or {}),
            "ok": not (
                isinstance(tool_result, dict) and tool_result.get("ok") is False
            ),
            "summary": summarize_tool_result(tool_name, tool_result),
        }
        if isinstance(tool_result, dict) and tool_result.get("error_type"):
            compact["error_type"] = tool_result["error_type"]
        return compact

    def rebuild_turn_messages_from_history(self, user_input, execution_history):
        # 断点续跑：从步进记录重建整轮消息列表。前缀用本轮记忆快照与
        # workspace 冻结一次，已完成步骤还原成 assistant/user 交换对，
        # 之后的新工具步继续在尾部追加。
        # 步进记录没有保存原生 tool_call id，无法还原合法的
        # assistant(tool_calls)/tool 序列：续跑轮统一走 json-protocol 兜底。
        self._turn_native_disabled = True
        memory = self._begin_turn_memory(user_input, [])
        self._set_plain_tool_context()
        head = self.prompt_builder.plain_answer_messages(
            user_input=user_input,
            memory=memory,
            workspace_context=self.workspace_context,
        )
        self._begin_turn_messages(head)
        for entry in execution_history or []:
            tool_call = dict((entry or {}).get("tool_call") or {})
            tool_result = (entry or {}).get("tool_result")
            self._append_turn_step(
                {"tool_call": tool_call, "tool_result": tool_result},
                assistant_text=self._synthesized_tool_call_text(tool_call),
            )
        self._fold_turn_messages_if_needed()
        return self._current_turn_messages()

    def _synthesized_tool_call_text(self, tool_call):
        # 步进记录没有保存模型原文，用工具调用 JSON 还原这一步的
        # assistant 消息，维持 assistant/user 交替结构。
        return json.dumps(
            {"type": "tool_call", **tool_call},
            ensure_ascii=False,
        )

    def _append_turn_step(self, entry, assistant_text, budget_notice=None):
        step_messages = [
            {"role": "assistant", "content": assistant_text},
            self.prompt_builder.observation_delta_message(
                {
                    "tool_call": entry["tool_call"],
                    "tool_result": entry["tool_result"],
                }
            ),
        ]
        if budget_notice:
            step_messages.append(
                self.prompt_builder.budget_notice_message(budget_notice)
            )
        self._turn_steps.append({"messages": step_messages, "entries": [entry]})

    def _run_with_observation_append(self, user_input, observation):
        observation = dict(observation or {})
        budget_notice = observation.pop("budget_notice", None)
        # 全量历史已经活在消息前缀里；就算旧调用方塞了进来也丢弃。
        observation.pop("execution_history", None)
        entry = {
            "tool_call": dict(observation.get("tool_call") or {}),
            "tool_result": observation.get("tool_result"),
        }
        entry_key = json.dumps(entry, ensure_ascii=False, sort_keys=True, default=str)
        if entry_key != self._turn_pending_entry:
            # pending 标记只在“已追加但模型调用尚未成功”期间存在：
            # provider 恢复用同一个观察重调时，直接原样重发消息列表，
            # 绝不追加重复的交换对。
            assistant_text = (
                self._turn_last_response
                or self._synthesized_tool_call_text(entry["tool_call"])
            )
            self._append_turn_step(
                entry,
                assistant_text=assistant_text,
                budget_notice=budget_notice,
            )
            self._fold_turn_messages_if_needed()
            self._turn_pending_entry = entry_key
        response = self._think_protocol_json(self._current_turn_messages())
        self._turn_pending_entry = None
        self._turn_last_response = response
        return response

    def _native_assistant_message(self, turn):
        # 原样回放模型这一步的输出：content 与 provider 返回的 raw
        # arguments 逐字节保留，维持前缀缓存与 provider 侧的合法序列。
        tool_calls = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.raw_arguments},
            }
            for call in getattr(turn, "tool_calls", ()) or ()
        ]
        message = {
            "role": "assistant",
            "content": str(getattr(turn, "content", "") or ""),
        }
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message

    def _native_tool_message(self, call, tool_result):
        try:
            content = json.dumps(tool_result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            content = str(tool_result)
        return {"role": "tool", "tool_call_id": call.id, "content": content}

    def _native_step_entries(self, exchanges):
        entries = []
        for call, tool_result in exchanges:
            arguments = (
                call.arguments
                if isinstance(call.arguments, dict)
                else {"raw_arguments": call.raw_arguments}
            )
            entries.append(
                {
                    "tool_call": {
                        "tool_name": call.name,
                        "arguments": dict(arguments),
                    },
                    "tool_result": tool_result,
                }
            )
        return entries

    def run_native_step(self, user_input, assistant_turn, exchanges, budget_notice=None):
        """原生 FC 工具步：追加标准 assistant(tool_calls) 消息和每个工具的
        role:'tool' 结果消息后继续本轮。与 provider 恢复共用 pending 去重：
        同一观察重调时逐字节重发同一消息列表，绝不追加重复交换对。"""
        entries = self._native_step_entries(exchanges)
        step_key = json.dumps(
            entries, ensure_ascii=False, sort_keys=True, default=str
        )
        if step_key != self._turn_pending_entry:
            step_messages = [self._native_assistant_message(assistant_turn)]
            step_messages.extend(
                self._native_tool_message(call, tool_result)
                for call, tool_result in exchanges
            )
            if budget_notice:
                step_messages.append(
                    self.prompt_builder.budget_notice_message(budget_notice)
                )
            self._turn_steps.append({"messages": step_messages, "entries": entries})
            self._fold_turn_messages_if_needed()
            self._turn_pending_entry = step_key
        response = self._think_turn(self._current_turn_messages())
        self._turn_pending_entry = None
        self._turn_last_response = response
        return response

    def run_with_observation(self, user_input, observation):
        if self.turn_messages_active():
            return self._run_with_observation_append(user_input, observation)

        # 无轮级状态（如测试直接调用）时退回单发构造。
        memory = self._turn_memory_context
        if memory is None:
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
        # Repairing JSON never needs the skill body, so only the lightweight
        # tool context rides along.
        messages = self.prompt_builder.protocol_repair_messages(
            raw_text=raw_text,
            error_message=str(error),
            allowed_types=allowed_types,
            execution_context=self.current_turn_tool_context(),
            execution_history=execution_history or [],
            stage=stage,
        )
        response = self._think_protocol_json(messages, usage_kind="auxiliary")
        if self.turn_messages_active():
            # 修复后的合法 JSON 才是这一步真正生效的模型输出：下一条
            # 追加的 assistant 消息应还原它，而不是无效的原始文本。
            self._turn_last_response = response
        return response

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

    def _stream_protocol_json_tracked(self, messages):
        # 流式轮首调用也要记住完整原文：后续观察步追加的 assistant
        # 消息需要还原模型上一步的输出。
        chunks = []
        for chunk in self._stream_protocol_json(messages):
            if chunk is not None:
                text = str(chunk)
                if text:
                    chunks.append(text)
            yield chunk
        self._turn_last_response = "".join(chunks)

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
