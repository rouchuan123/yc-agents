import json
import time
from dataclasses import replace

from yc_agents.core.exceptions import LLMCallError, TruncatedOutputError
from yc_agents.harness.context import RunContext
from yc_agents.harness.trace import TraceRecorder
from yc_agents.harness.run_outputs import RunOutputWriter
from yc_agents.harness.json_protocol import (
    InvalidModelJSONError,
    extract_model_json,
    parse_model_json,
)
from yc_agents.harness.process_events import (
    assistant_step_entry,
    summarize_tool_result,
    tool_call_entry,
    tool_result_entry,
)
from yc_agents.harness.recovery import (
    RecoveryController,
    RecoveryPolicy,
    RunStoppedError,
)
from yc_agents.harness.state import StateStore
from yc_agents.harness.tool_gateway import ToolGateway, ToolNotAllowedError
from yc_agents.harness.tool_policy import ToolExecutionPolicy
from yc_agents.harness.token_budget import TokenBudget, TokenBudgetPolicy
from yc_agents.harness.verification import VerificationGate


RUNTIME_RESPONSE_TYPES = {"tool_call", "final_answer"}
FINAL_AFTER_TOOL_TYPES = {"tool_call", "final_answer"}
STEP_RESULT_SNAPSHOT_LIMIT = 2000


class RunResult(str):
    """最终文本的 str 子类：老调用方仍可当纯文本用，新调用方直接读
    status/run_id/verification 等元数据，不必再侧信道重读磁盘。"""

    def __new__(
        cls,
        text,
        *,
        status="finished",
        run_id=None,
        run_dir=None,
        verification=None,
        stop_reason=None,
        artifacts=None,
    ):
        result = super().__new__(cls, "" if text is None else str(text))
        result.status = status
        result.run_id = run_id
        result.run_dir = run_dir
        result.verification = verification
        result.stop_reason = stop_reason
        result.artifacts = list(artifacts or [])
        return result


class YCAgentRuntime:
    def __init__(
        self,
        agent,
        expects_json=False,
        tool_registry=None,
        allowed_tools=None,
        approval_gate=None,
        approval_callback=None,
        verification_gate=None,
        output_root=None,
        event_callback=None,
        tool_policy=None,
        analytics_recorder=None,
        managed_resources=None,
        recovery_policy=None,
        invalid_json_retry_count=0,
        fail_on_invalid_json=False,
        context_limit=8000,
        token_budget_policy=None,
        tool_calling="json-protocol",
    ):
        self.agent = agent
        self.expects_json = expects_json
        self.tool_registry = tool_registry
        self.allowed_tools = allowed_tools or []
        self.approval_gate = approval_gate
        # 审批回调可由 TUI 在构造后注入（runtime.approval_callback = ...），
        # gateway 每次工具调用时读取最新值。
        self.approval_callback = approval_callback
        self.verification_gate = verification_gate or VerificationGate()
        self.output_root = output_root
        self.event_callback = event_callback
        self.tool_policy = tool_policy
        self.analytics_recorder = analytics_recorder
        self.managed_resources = list(managed_resources or [])
        self.invalid_json_retry_count = invalid_json_retry_count
        self.recovery_policy = recovery_policy or RecoveryPolicy(
            protocol_retries=invalid_json_retry_count,
            provider_retries=0,
            verification_retries=0,
            max_attempts=max(4, int(invalid_json_retry_count or 0)),
        )
        self.fail_on_invalid_json = fail_on_invalid_json
        self.context_limit = int(context_limit or 8000)
        self.token_budget_policy = token_budget_policy or TokenBudgetPolicy()
        # 'native'：模型走原生 function calling 工具循环；其余值一律走
        # json-protocol 文本协议。native 只有在 agent 也配置了 tools 时生效。
        self.tool_calling = str(tool_calling or "json-protocol")
        if analytics_recorder is not None:
            self.managed_resources.append(analytics_recorder)
        self.last_trace_events = []
        self.last_run_id = None
        self.last_run_dir = None

    def run(self, user_input):
        context = RunContext(user_input=user_input, output_root=self.output_root)
        self.last_run_id = context.run_id
        self.last_run_dir = context.outputs_dir
        run_analytics = self._start_run_analytics(context)
        usage_baseline = self._snapshot_run_usage()
        budget_meter = self._start_budget_meter()
        trace = TraceRecorder(
            context,
            event_callback=self._build_event_callback(run_analytics),
            propagate_callback_errors=bool(getattr(run_analytics, "strict", False)),
        )
        writer = RunOutputWriter(context)
        state_store = StateStore(context.outputs_dir / "state.json")

        try:
            trace.record("run_started")
            state_store.save_checkpoint("run_started", "running", {"user_input": user_input})
            writer.write_input()
            writer.write_context(self._build_context_snapshot(context))
            process_entries = []
            recorded_selected_skill = set()
            execution_history = []
            recovery = RecoveryController(self.recovery_policy)

            response = self._initial_model_response(
                user_input,
                stage="initial",
                trace=trace,
                state_store=state_store,
                process_entries=process_entries,
                recovery=recovery,
            )
            trace.record("model_called")
            self._record_selected_skill(
                trace,
                recorded_selected_skill,
                process_entries,
            )
            state_store.save_checkpoint("model_called", "running")

            if self.expects_json:
                response = self._run_tool_loop(
                    trace,
                    user_input,
                    response,
                    recorded_selected_skill,
                    process_entries,
                    execution_history,
                    recovery,
                    state_store,
                    budget_meter=budget_meter,
                )

            response, verification = self._verify_with_recovery(
                user_input=user_input,
                response=response,
                execution_history=execution_history,
                trace=trace,
                state_store=state_store,
                process_entries=process_entries,
                recovery=recovery,
            )
            return self._finalize_run(
                context=context,
                user_input=user_input,
                response=response,
                verification=verification,
                execution_history=execution_history,
                process_entries=process_entries,
                trace=trace,
                state_store=state_store,
                writer=writer,
                run_analytics=run_analytics,
                usage_baseline=usage_baseline,
            )
        except RunStoppedError as exc:
            return self._finish_stopped_run(
                user_input=user_input,
                error=exc,
                process_entries=process_entries,
                trace=trace,
                state_store=state_store,
                writer=writer,
                run_analytics=run_analytics,
                usage_baseline=usage_baseline,
                execution_history=execution_history,
            )
        except Exception as exc:
            if run_analytics is not None:
                self._record_run_token_usage(run_analytics, usage_baseline)
                run_analytics.finish(
                    "failed",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
            self._record_run_failed(trace, state_store, exc)
            raise

    def stream(self, user_input):
        stream_agent = getattr(self.agent, "stream", None)

        if not callable(stream_agent):
            yield self.run(user_input)
            return

        context = RunContext(user_input=user_input, output_root=self.output_root)
        self.last_run_id = context.run_id
        self.last_run_dir = context.outputs_dir
        run_analytics = self._start_run_analytics(context)
        usage_baseline = self._snapshot_run_usage()
        budget_meter = self._start_budget_meter()
        trace = TraceRecorder(
            context,
            event_callback=self._build_event_callback(run_analytics),
            propagate_callback_errors=bool(getattr(run_analytics, "strict", False)),
        )
        writer = RunOutputWriter(context)
        state_store = StateStore(context.outputs_dir / "state.json")

        try:
            trace.record("run_started")
            state_store.save_checkpoint("run_started", "running", {"user_input": user_input})
            writer.write_input()
            writer.write_context(self._build_context_snapshot(context))
            process_entries = []
            recorded_selected_skill = set()
            execution_history = []
            recovery = RecoveryController(self.recovery_policy)

            chunks = []
            buffered_for_json = self.expects_json

            if buffered_for_json:
                if self._native_mode_active() and self._agent_native_enabled():
                    # 原生 FC 需要结构化 tool_calls，流式增量只有文本；
                    # 首调改为非流式整回合调用，工具循环之后与 run() 一致。
                    response = self._initial_model_response(
                        user_input,
                        stage="initial_stream",
                        trace=trace,
                        state_store=state_store,
                        process_entries=process_entries,
                        recovery=recovery,
                    )
                else:
                    response = self._call_model_with_recovery(
                        lambda: "".join(
                            str(chunk)
                            for chunk in stream_agent(user_input)
                            if chunk is not None and str(chunk)
                        ),
                        stage="initial_stream",
                        trace=trace,
                        state_store=state_store,
                        process_entries=process_entries,
                        recovery=recovery,
                    )
            else:
                for chunk in stream_agent(user_input):
                    if chunk is None:
                        continue
                    text = str(chunk)
                    if not text:
                        continue
                    chunks.append(text)
                    yield text
                response = "".join(chunks)
            trace.record("model_called")
            self._record_selected_skill(
                trace,
                recorded_selected_skill,
                process_entries,
            )
            state_store.save_checkpoint("model_called", "running")

            if self.expects_json and buffered_for_json:
                response = self._run_tool_loop(
                    trace,
                    user_input,
                    response,
                    recorded_selected_skill,
                    process_entries,
                    execution_history,
                    recovery,
                    state_store,
                    budget_meter=budget_meter,
                )

            if buffered_for_json:
                response, verification = self._verify_with_recovery(
                    user_input=user_input,
                    response=response,
                    execution_history=execution_history,
                    trace=trace,
                    state_store=state_store,
                    process_entries=process_entries,
                    recovery=recovery,
                )
            else:
                verification = self.verification_gate.verify_final_output(
                    response,
                    execution_history=execution_history,
                )

            run_result = self._finalize_run(
                context=context,
                user_input=user_input,
                response=response,
                verification=verification,
                execution_history=execution_history,
                process_entries=process_entries,
                trace=trace,
                state_store=state_store,
                writer=writer,
                run_analytics=run_analytics,
                usage_baseline=usage_baseline,
            )
            if buffered_for_json:
                yield run_result
        except RunStoppedError as exc:
            response = self._finish_stopped_run(
                user_input=user_input,
                error=exc,
                process_entries=process_entries,
                trace=trace,
                state_store=state_store,
                writer=writer,
                run_analytics=run_analytics,
                usage_baseline=usage_baseline,
                execution_history=execution_history,
            )
            yield response
        except Exception as exc:
            if run_analytics is not None:
                self._record_run_token_usage(run_analytics, usage_baseline)
                run_analytics.finish(
                    "failed",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
            self._record_run_failed(trace, state_store, exc)
            raise

    def resume_from_state(self, state_path, redirect_instruction=None):
        state_store = StateStore(state_path)
        checkpoint = state_store.latest_checkpoint()

        if checkpoint is None:
            return "No checkpoint available to resume."

        user_input = self._resume_user_input(state_store, checkpoint)

        if not user_input:
            return "Checkpoint does not contain user input; cannot resume safely."

        if redirect_instruction:
            user_input = f"{user_input}\n\n用户追加指令：{redirect_instruction}"

        steps = state_store.load_steps()
        if (
            steps
            and self.expects_json
            and callable(getattr(self.agent, "run_with_observation", None))
        ):
            return self._resume_from_steps(user_input, steps)

        return self.run(user_input)

    def _resume_user_input(self, state_store, checkpoint):
        user_input = checkpoint.get("details", {}).get("user_input")
        if user_input:
            return user_input

        # 停止的运行最后一个 checkpoint 通常是 run_finished/failed，
        # user_input 记录在更早的 run_started checkpoint 里，向前回溯。
        for entry in reversed(state_store.load().get("history", [])):
            candidate = (entry.get("details") or {}).get("user_input")
            if candidate:
                return candidate
        return None

    def _resume_from_steps(self, user_input, steps):
        context = RunContext(user_input=user_input, output_root=self.output_root)
        self.last_run_id = context.run_id
        self.last_run_dir = context.outputs_dir
        run_analytics = self._start_run_analytics(context)
        usage_baseline = self._snapshot_run_usage()
        budget_meter = self._start_budget_meter()
        trace = TraceRecorder(
            context,
            event_callback=self._build_event_callback(run_analytics),
            propagate_callback_errors=bool(getattr(run_analytics, "strict", False)),
        )
        writer = RunOutputWriter(context)
        state_store = StateStore(context.outputs_dir / "state.json")

        try:
            trace.record("run_started")
            state_store.save_checkpoint(
                "run_started",
                "running",
                {"user_input": user_input, "resumed_steps": len(steps)},
            )
            writer.write_input()
            writer.write_context(self._build_context_snapshot(context))
            process_entries = []
            recorded_selected_skill = set()
            execution_history = []
            recovery = RecoveryController(self.recovery_policy)

            for step in steps:
                entry = {
                    "tool_call": dict(step.get("tool_call") or {}),
                    "tool_result": step.get("tool_result"),
                }
                execution_history.append(entry)
                state_store.append_step(
                    self._build_step_record(
                        len(execution_history) - 1,
                        entry["tool_call"],
                        entry["tool_result"],
                    )
                )
            trace.record("run_resumed", {"replayed_steps": len(execution_history)})

            # 重放历史后，把最后一个完成的工具结果作为观察直接续跑工具
            # 循环，而不是整轮重跑。轮级消息 agent 先从步进记录重建整轮
            # 消息前缀，最后一步作为观察增量继续追加；旧式 agent 仍走
            # 观察内嵌历史的单发构造。
            last = execution_history[-1]
            rebuild = getattr(
                self.agent, "rebuild_turn_messages_from_history", None
            )
            if callable(rebuild):
                rebuild(user_input, execution_history[:-1])
                observation = {
                    "tool_call": last["tool_call"],
                    "tool_result": last["tool_result"],
                }
            else:
                observation = {
                    "tool_call": last["tool_call"],
                    "tool_result": last["tool_result"],
                    "execution_history": self._history_for_observation(
                        execution_history[:-1]
                    ),
                }
            response = self._call_model_with_recovery(
                lambda: self.agent.run_with_observation(user_input, observation),
                stage="resume_observation",
                trace=trace,
                state_store=state_store,
                process_entries=process_entries,
                recovery=recovery,
            )
            trace.record("model_called")
            self._record_selected_skill(
                trace,
                recorded_selected_skill,
                process_entries,
            )
            state_store.save_checkpoint("model_called", "running")

            response = self._handle_json_response(
                trace,
                user_input,
                response,
                recorded_selected_skill,
                process_entries,
                execution_history,
                recovery,
                state_store,
                budget_meter=budget_meter,
            )

            response, verification = self._verify_with_recovery(
                user_input=user_input,
                response=response,
                execution_history=execution_history,
                trace=trace,
                state_store=state_store,
                process_entries=process_entries,
                recovery=recovery,
            )
            return self._finalize_run(
                context=context,
                user_input=user_input,
                response=response,
                verification=verification,
                execution_history=execution_history,
                process_entries=process_entries,
                trace=trace,
                state_store=state_store,
                writer=writer,
                run_analytics=run_analytics,
                usage_baseline=usage_baseline,
            )
        except RunStoppedError as exc:
            return self._finish_stopped_run(
                user_input=user_input,
                error=exc,
                process_entries=process_entries,
                trace=trace,
                state_store=state_store,
                writer=writer,
                run_analytics=run_analytics,
                usage_baseline=usage_baseline,
                execution_history=execution_history,
            )
        except Exception as exc:
            if run_analytics is not None:
                self._record_run_token_usage(run_analytics, usage_baseline)
                run_analytics.finish(
                    "failed",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
            self._record_run_failed(trace, state_store, exc)
            raise

    def _build_context_snapshot(self, context):
        return {
            "run_id": context.run_id,
            "created_at": context.created_at,
            "user_input": context.user_input,
            "selected_skill": context.selected_skill,
            "intent_result": context.intent_result,
            "enabled_tools": list(self.allowed_tools),
            "expects_json": self.expects_json,
        }

    def _remember_turn(self, user_input, response):
        remember_turn = getattr(self.agent, "remember_turn", None)

        if remember_turn is None:
            return None

        return remember_turn(user_input, response)

    def _start_run_analytics(self, context):
        if self.analytics_recorder is None:
            return None

        return self.analytics_recorder.start_run(context)

    def _usage_ledger(self):
        llm = getattr(self.agent, "llm", None)
        return getattr(llm, "usage_ledger", None)

    def _start_budget_meter(self):
        return self.token_budget_policy.start_meter(self._usage_ledger())

    def _snapshot_run_usage(self):
        totals = getattr(self._usage_ledger(), "session_totals", None)
        if totals is None:
            return None
        return {
            name: int(getattr(totals, name, 0) or 0)
            for name in (
                "input_tokens",
                "output_tokens",
                "cached_tokens",
                "total_tokens",
            )
        }

    def _record_run_token_usage(self, run_analytics, usage_baseline):
        if run_analytics is None or usage_baseline is None:
            return
        current = self._snapshot_run_usage()
        if current is None:
            return
        delta = {
            name: max(0, current[name] - usage_baseline[name])
            for name in usage_baseline
        }
        record = getattr(run_analytics, "record_token_usage", None)
        if callable(record):
            record(delta)

    def _check_token_budget(self, budget_meter, trace):
        if budget_meter is None:
            return None
        status = budget_meter.check()
        if status is None:
            return None
        if status["level"] == "hard":
            trace.record("budget_hard_exceeded", dict(status))
            raise RunStoppedError(
                "本次运行 token 消耗已达硬预算上限"
                f"（约 {status['run_tokens']}/{status['limit']}），已停止继续调用工具并保留局部结果。"
                "可在 ycore.json 的 runtime.tokenBudget.hardTokens 调高预算，或把任务拆小后重试。",
                kind="budget",
                stage="tool_loop",
                error_type="token_budget_exhausted",
            )
        trace.record("budget_soft_exceeded", dict(status))
        return budget_meter.soft_notice()

    def _build_event_callback(self, run_analytics):
        def callback(event):
            if run_analytics is not None:
                run_analytics.record_event(event)
            if self.event_callback is not None:
                try:
                    self.event_callback(event)
                except Exception:
                    pass

        return callback

    def close(self):
        for resource in reversed(self.managed_resources):
            close = getattr(resource, "close", None)
            if callable(close):
                close()

    def shutdown(self):
        self.close()

    def _emit_process_entry(self, trace, process_entries, entry):
        if not entry:
            return
        process_entries.append(entry)
        trace.record("assistant_process", {"entry": entry})

    def _remember_completed_turn(self, user_input, response, process_entries):
        remember_structured = getattr(self.agent, "remember_structured_turn", None)
        if callable(remember_structured):
            return remember_structured(user_input, response, process_entries)
        return self._remember_turn(user_input, response)

    # ------------------------------------------------------------------
    # 原生 function calling 工具循环：tools 数组随消息进入 think，模型的
    # 结构化 tool_calls 直接执行，跳过 extract_model_json/协议修复整条链路；
    # json-protocol 循环原样保留为默认与兜底。
    # ------------------------------------------------------------------

    def _native_mode_active(self):
        return self.tool_calling == "native"

    def _agent_native_enabled(self):
        enabled = getattr(self.agent, "native_tools_enabled", None)
        return callable(enabled) and bool(enabled())

    def _agent_native_turn_active(self):
        active = getattr(self.agent, "native_turn_active", None)
        return callable(active) and bool(active())

    def _initial_model_response(
        self,
        user_input,
        *,
        stage,
        trace,
        state_store,
        process_entries,
        recovery,
    ):
        def call_agent():
            return self.agent.run(user_input)

        if not (self._native_mode_active() and self._agent_native_enabled()):
            return self._call_model_with_recovery(
                call_agent,
                stage=stage,
                trace=trace,
                state_store=state_store,
                process_entries=process_entries,
                recovery=recovery,
            )

        try:
            return self._call_model_with_recovery(
                call_agent,
                stage=stage,
                trace=trace,
                state_store=state_store,
                process_entries=process_entries,
                recovery=recovery,
            )
        except RunStoppedError as exc:
            if exc.error_type != "ToolCallingUnsupported":
                raise
            # provider 不认 tools 参数：本轮自动降级 json-protocol 重跑，
            # 而不是让整次运行失败；下一轮会重新尝试原生 FC。
            details = {"stage": stage, "error": str(exc)}
            trace.record("native_fc_fallback", details)
            state_store.save_checkpoint("native_fc_fallback", "running", details)
            disable = getattr(self.agent, "disable_native_for_turn", None)
            if callable(disable):
                disable()
            return self._call_model_with_recovery(
                call_agent,
                stage=stage,
                trace=trace,
                state_store=state_store,
                process_entries=process_entries,
                recovery=recovery,
            )

    def _run_tool_loop(
        self,
        trace,
        user_input,
        response,
        recorded_selected_skill,
        process_entries,
        execution_history,
        recovery,
        state_store,
        budget_meter=None,
    ):
        if self._native_mode_active() and self._agent_native_turn_active():
            return self._handle_native_response(
                trace,
                user_input,
                response,
                recorded_selected_skill,
                process_entries,
                execution_history,
                recovery,
                state_store,
                budget_meter=budget_meter,
            )
        return self._handle_json_response(
            trace,
            user_input,
            response,
            recorded_selected_skill,
            process_entries,
            execution_history,
            recovery,
            state_store,
            budget_meter=budget_meter,
        )

    def _handle_native_response(
        self,
        trace,
        user_input,
        response,
        recorded_selected_skill,
        process_entries,
        execution_history,
        recovery,
        state_store,
        budget_meter=None,
    ):
        policy = self._new_tool_policy()
        terminal_delivery = False

        while True:
            tool_calls = list(getattr(response, "tool_calls", None) or [])
            if not tool_calls:
                # 无 tool_calls 的纯 content 即最终答案，无需 final_answer
                # JSON 包装。
                return self._native_final_content(response)

            if terminal_delivery:
                trace.record(
                    "terminal_tool_call_blocked",
                    {
                        "reason": "document_delivery_complete",
                        "tool_names": [call.name for call in tool_calls],
                    },
                )
                return self._terminal_delivery_final(execution_history)

            response, step_terminal = self._handle_native_tool_step(
                trace,
                user_input,
                response,
                tool_calls,
                policy,
                recorded_selected_skill,
                process_entries,
                execution_history,
                recovery,
                state_store,
                budget_meter=budget_meter,
            )
            terminal_delivery = terminal_delivery or step_terminal

    def _native_final_content(self, response):
        if hasattr(response, "content"):
            return str(response.content or "")
        return str(response or "")

    def _handle_native_tool_step(
        self,
        trace,
        user_input,
        response,
        tool_calls,
        policy,
        recorded_selected_skill,
        process_entries,
        execution_history,
        recovery,
        state_store,
        budget_meter=None,
    ):
        budget_notice = self._check_token_budget(budget_meter, trace)
        self._emit_process_entry(
            trace,
            process_entries,
            assistant_step_entry(getattr(response, "content", "")),
        )

        gateway = ToolGateway(
            tool_registry=self.tool_registry,
            allowed_tools=self._effective_allowed_tools(trace),
            trace=trace,
            approval_gate=self.approval_gate,
            approval_callback=self.approval_callback,
            policy=policy,
        )

        exchanges = []
        tool_recoveries = []
        terminal_delivery = False
        for call in tool_calls:
            self._emit_process_entry(
                trace,
                process_entries,
                tool_call_entry(call.name),
            )
            call_data = self._native_tool_call_data(call)
            trace.record("tool_call_requested", call_data)

            if terminal_delivery:
                tool_result = {
                    "ok": False,
                    "error": "DOCUMENT_WORKFLOW_TERMINAL",
                    "error_type": "expected_workflow_state",
                    "terminal": True,
                    "workflow_complete": True,
                    "next_action": "final_answer",
                    "instruction": (
                        "A document version was already published in this user turn. "
                        "This additional tool call was not executed; return the final answer."
                    ),
                }
            elif not getattr(call, "arguments_valid", False):
                # arguments 坏 JSON 属于 tool_feedback 类恢复：把错误作为
                # 工具结果反馈让模型重试同一调用，绝不送去 JSON 协议修复。
                tool_result = {
                    "ok": False,
                    "tool_name": call.name,
                    "error_type": "invalid_tool_arguments",
                    "error": (
                        f"工具 {call.name} 的 arguments 不是合法 JSON 对象"
                        f"（{call.parse_error or 'arguments 必须是 JSON 对象'}）。"
                        "请重新发起同一工具调用，arguments 必须是与参数 "
                        "schema 匹配的 JSON 对象。"
                    ),
                }
            else:
                try:
                    tool_result = gateway.run_tool(call.name, **call.arguments)
                except ToolNotAllowedError as exc:
                    raise RunStoppedError(
                        str(exc),
                        kind="tool",
                        stage="tool_call",
                        error_type="tool_not_allowed",
                    ) from exc

            self._emit_process_entry(
                trace,
                process_entries,
                tool_result_entry(call.name, tool_result),
            )
            execution_history.append(
                {
                    "tool_call": call_data,
                    "tool_result": tool_result,
                }
            )
            if self._tool_result_is_terminal_delivery(tool_result):
                terminal_delivery = True
                trace.record(
                    "document_delivery_terminal",
                    {
                        "version": tool_result.get("version"),
                        "published_path": tool_result.get("published_path"),
                    },
                )

            if self._tool_loop_was_stopped(tool_result):
                raise RunStoppedError(
                    self._tool_loop_stopped_message(tool_result),
                    kind="tool",
                    stage="tool_call",
                    error_type="loop_stopped",
                )

            expected_followup = self._tool_result_is_expected_followup(tool_result)
            if self._tool_result_failed(tool_result) and not expected_followup:
                # approval_denied 不在停机名单里：审批拒绝作为普通工具失败
                # 回喂模型改道，绝不丢弃整轮进度。
                error_type = tool_result.get("error_type", "tool_error")
                if error_type == "permission_error":
                    raise RunStoppedError(
                        self._tool_failure_message(tool_result),
                        kind="tool",
                        stage="tool_call",
                        error_type=error_type,
                    )
                tool_recoveries.append(
                    self._reserve_recovery(
                        kind="tool_feedback",
                        stage="tool_observation",
                        error_type=error_type,
                        error=self._tool_failure_message(tool_result),
                        trace=trace,
                        state_store=state_store,
                        process_entries=process_entries,
                        recovery=recovery,
                    )
                )
            else:
                recovery.reset("tool_feedback")

            state_store.append_step(
                self._build_step_record(
                    len(execution_history) - 1,
                    call_data,
                    tool_result,
                )
            )
            exchanges.append((call, tool_result))

        follow_up = self._call_model_with_recovery(
            lambda: self.agent.run_native_step(
                user_input,
                response,
                exchanges,
                budget_notice=budget_notice,
                final_only=terminal_delivery,
            ),
            stage="tool_observation",
            trace=trace,
            state_store=state_store,
            process_entries=process_entries,
            recovery=recovery,
        )
        trace.record("model_called")
        self._record_selected_skill(
            trace,
            recorded_selected_skill,
            process_entries,
        )
        for info in tool_recoveries:
            self._record_recovery_succeeded(
                info,
                trace=trace,
                state_store=state_store,
                recovery=recovery,
            )
        return follow_up, terminal_delivery

    def _native_tool_call_data(self, call):
        data = {
            "type": "tool_call",
            "tool_name": call.name,
            "tool_call_id": call.id,
            "arguments": call.arguments if isinstance(call.arguments, dict) else {},
        }
        if call.parse_error is not None:
            data["raw_arguments"] = call.raw_arguments
            data["arguments_parse_error"] = call.parse_error
        return data

    def _handle_json_response(
        self,
        trace,
        user_input,
        response,
        recorded_selected_skill,
        process_entries,
        execution_history,
        recovery,
        state_store,
        budget_meter=None,
    ):
        policy = self._new_tool_policy()

        while True:
            response = self._handle_json_response_once(
                trace,
                user_input,
                response,
                policy,
                recorded_selected_skill,
                process_entries,
                execution_history,
                recovery,
                state_store,
                budget_meter=budget_meter,
            )

            if not self._is_tool_call_json(response):
                return response

    def _handle_json_response_once(
        self,
        trace,
        user_input,
        response,
        policy,
        recorded_selected_skill,
        process_entries,
        execution_history,
        recovery,
        state_store,
        budget_meter=None,
    ):
        response, preface, data = self._parse_with_protocol_recovery(
            response=response,
            allowed_types=RUNTIME_RESPONSE_TYPES,
            user_input=user_input,
            stage="runtime_response",
            trace=trace,
            state_store=state_store,
            process_entries=process_entries,
            recovery=recovery,
            execution_history=execution_history,
        )
        if data is None:
            return response

        self._emit_process_entry(
            trace,
            process_entries,
            assistant_step_entry(preface),
        )

        if data["type"] == "tool_call":
            return self._handle_tool_call(
                trace,
                user_input,
                data,
                policy,
                recorded_selected_skill,
                process_entries,
                execution_history,
                recovery,
                state_store,
                budget_meter=budget_meter,
            )

        if data["type"] == "final_answer":
            return data.get("content", "")

        return response

    def _runtime_expectation(self):
        return {"allowed_types": sorted(RUNTIME_RESPONSE_TYPES)}

    def _call_model_with_recovery(
        self,
        callback,
        *,
        stage,
        trace,
        state_store,
        process_entries,
        recovery,
    ):
        retry_info = None
        escalated_llm = None
        try:
            while True:
                try:
                    result = callback()
                except TruncatedOutputError as exc:
                    # 截断不是协议错误：先免费提额重试一次，仍截断才消耗
                    # provider 恢复预算，绝不送去 JSON 协议修复。
                    if escalated_llm is None:
                        escalated_llm = self._escalate_output_budget(
                            exc,
                            stage=stage,
                            trace=trace,
                        )
                        if escalated_llm is not None:
                            continue
                    retry_info = self._reserve_provider_recovery(
                        exc,
                        stage=stage,
                        trace=trace,
                        state_store=state_store,
                        process_entries=process_entries,
                        recovery=recovery,
                    )
                    self._sleep_before_provider_retry(retry_info)
                    continue
                except LLMCallError as exc:
                    if not exc.retryable:
                        raise RunStoppedError(
                            str(exc),
                            kind="provider",
                            stage=stage,
                            error_type=exc.cause_type or exc.__class__.__name__,
                        ) from exc
                    retry_info = self._reserve_provider_recovery(
                        exc,
                        stage=stage,
                        trace=trace,
                        state_store=state_store,
                        process_entries=process_entries,
                        recovery=recovery,
                    )
                    self._sleep_before_provider_retry(retry_info)
                    continue
                finally:
                    # ModelRouter 在链内切换 fallback 后把切换事件挂在
                    # llm 上；无论本次调用成功与否都要落进 trace。
                    self._drain_model_switch_events(trace)

                if retry_info is not None:
                    self._record_recovery_succeeded(
                        retry_info,
                        trace=trace,
                        state_store=state_store,
                        recovery=recovery,
                    )
                return result
        finally:
            if escalated_llm is not None:
                escalated_llm.clear_call_overrides()

    def _drain_model_switch_events(self, trace):
        llm = getattr(self.agent, "llm", None)
        consume = getattr(llm, "consume_switch_events", None)
        if not callable(consume):
            return
        try:
            events = consume() or []
        except Exception:
            return
        for event in events:
            trace.record("model_switched", dict(event))

    def _reserve_provider_recovery(
        self,
        exc,
        *,
        stage,
        trace,
        state_store,
        process_entries,
        recovery,
    ):
        return self._reserve_recovery(
            kind="provider",
            stage=stage,
            error_type=exc.cause_type or exc.__class__.__name__,
            error=str(exc),
            trace=trace,
            state_store=state_store,
            process_entries=process_entries,
            recovery=recovery,
        )

    def _sleep_before_provider_retry(self, retry_info):
        delay = max(
            0.0,
            float(self.recovery_policy.provider_backoff_seconds),
        ) * retry_info["attempt"]
        if delay:
            time.sleep(delay)

    def _escalate_output_budget(self, exc, *, stage, trace):
        llm = getattr(self.agent, "llm", None)
        set_overrides = getattr(llm, "set_call_overrides", None)
        clear_overrides = getattr(llm, "clear_call_overrides", None)
        if not callable(set_overrides) or not callable(clear_overrides):
            return None
        provider_max = getattr(
            getattr(llm, "config", None),
            "max_output_tokens",
            None,
        )
        cap = max(int(provider_max or 0) * 2, 8192)
        current = int(exc.max_tokens or 0)
        escalated = min(current * 2, cap) if current > 0 else cap
        if escalated <= current:
            return None
        set_overrides(max_tokens=escalated)
        trace.record(
            "truncated_output_retry",
            {
                "stage": stage,
                "max_tokens": current or None,
                "retry_max_tokens": escalated,
            },
        )
        return llm

    def _parse_with_protocol_recovery(
        self,
        *,
        response,
        allowed_types,
        user_input,
        stage,
        trace,
        state_store,
        process_entries,
        recovery,
        execution_history=None,
    ):
        retry_info = None
        while True:
            try:
                preface, data = extract_model_json(
                    response,
                    allowed_types=allowed_types,
                )
            except InvalidModelJSONError as exc:
                trace.record(
                    "invalid_model_json",
                    {"error": str(exc), "raw_text": exc.raw_text, "stage": stage},
                )
                try:
                    retry_info = self._reserve_recovery(
                        kind="protocol",
                        stage=stage,
                        error_type=exc.__class__.__name__,
                        error=str(exc),
                        trace=trace,
                        state_store=state_store,
                        process_entries=process_entries,
                        recovery=recovery,
                    )
                except RunStoppedError:
                    if self.fail_on_invalid_json:
                        raise
                    return response, "", None

                response = self._call_model_with_recovery(
                    lambda: self._retry_after_invalid_json(
                        user_input,
                        exc,
                        expectation={"allowed_types": sorted(allowed_types)},
                        stage=stage,
                        # 修复调用才真正需要压缩历史；正常步骤不再为它
                        # 每步全量重算 raw/compact。
                        execution_history=self._history_for_observation(
                            list(execution_history or [])
                        ),
                    ),
                    stage="protocol_repair",
                    trace=trace,
                    state_store=state_store,
                    process_entries=process_entries,
                    recovery=recovery,
                )
                trace.record("model_called", {"stage": "protocol_repair"})
                continue

            if retry_info is not None:
                self._record_recovery_succeeded(
                    retry_info,
                    trace=trace,
                    state_store=state_store,
                    recovery=recovery,
                )
            return response, preface, data

    def _reserve_recovery(
        self,
        *,
        kind,
        stage,
        error_type,
        error,
        trace,
        state_store,
        process_entries,
        recovery,
    ):
        info = recovery.reserve(kind)
        summary = str(error or error_type).strip()[:300]
        if info is None:
            details = {
                "kind": kind,
                "stage": stage,
                "error_type": error_type,
                "error": summary,
                **recovery.snapshot(),
            }
            lifetime_check = getattr(recovery, "lifetime_exhausted", None)
            event = (
                "recovery_lifetime_exhausted"
                if callable(lifetime_check) and lifetime_check()
                else "recovery_exhausted"
            )
            trace.record(event, details)
            state_store.save_checkpoint(event, "failed", details)
            raise RunStoppedError(
                summary,
                kind=kind,
                stage=stage,
                error_type=error_type,
                exhausted=True,
            )

        details = {
            **info,
            "stage": stage,
            "error_type": error_type,
            "error": summary,
        }
        trace.record("recovery_attempt", details)
        state_store.save_checkpoint("recovery_attempt", "running", details)
        self._emit_process_entry(
            trace,
            process_entries,
            assistant_step_entry(self._recovery_process_message(details)),
        )
        return details

    def _record_recovery_succeeded(self, info, *, trace, state_store, recovery=None):
        trace.record("recovery_succeeded", dict(info))
        state_store.save_checkpoint("recovery_succeeded", "running", dict(info))
        if recovery is not None:
            # 恢复成功即打断连败：释放该 kind 与全局连败计数，把预算留给
            # 之后的新故障；终身预算仍在累计，防止无限抖动。
            recovery.record_success(info.get("kind"))

    def _recovery_process_message(self, details):
        labels = {
            "protocol": "模型输出格式不符合协议，正在修复",
            "provider": "模型服务暂时不可用，正在重试",
            "tool_feedback": "工具执行失败，正在让 Agent 调整下一步",
            "verification": "最终回答未通过验证，正在修订",
        }
        label = labels.get(details.get("kind"), "正在尝试恢复")
        return f"{label}（{details.get('attempt')}/{details.get('limit')}）。"

    def _retry_after_invalid_json(
        self,
        user_input,
        error,
        expectation=None,
        stage=None,
        execution_history=None,
    ):
        retry = getattr(self.agent, "run_with_protocol_error", None)
        if callable(retry):
            try:
                return retry(
                    user_input,
                    error,
                    expectation=expectation,
                    execution_history=execution_history or [],
                    stage=stage,
                )
            except TypeError:
                try:
                    return retry(user_input, error, expectation=expectation)
                except TypeError:
                    return retry(user_input, error)

        return self.agent.run(
            user_input
            + "\n\n系统提示：上一条模型输出不是合法 JSON。请只返回符合协议的 JSON，不要输出 Markdown 代码块或额外解释。"
        )

    def _handle_tool_call(
        self,
        trace,
        user_input,
        data,
        policy,
        recorded_selected_skill,
        process_entries,
        execution_history,
        recovery,
        state_store,
        budget_meter=None,
    ):
        budget_notice = self._check_token_budget(budget_meter, trace)
        self._emit_process_entry(
            trace,
            process_entries,
            assistant_step_entry(data.get("message")),
        )
        self._emit_process_entry(
            trace,
            process_entries,
            tool_call_entry(data.get("tool_name")),
        )
        trace.record("tool_call_requested", data)

        gateway = ToolGateway(
            tool_registry=self.tool_registry,
            allowed_tools=self._effective_allowed_tools(trace),
            trace=trace,
            approval_gate=self.approval_gate,
            approval_callback=self.approval_callback,
            policy=policy,
        )

        try:
            tool_result = gateway.run_tool(
                data["tool_name"],
                **data["arguments"],
            )
        except ToolNotAllowedError as exc:
            raise RunStoppedError(
                str(exc),
                kind="tool",
                stage="tool_call",
                error_type="tool_not_allowed",
            ) from exc
        self._emit_process_entry(
            trace,
            process_entries,
            tool_result_entry(data.get("tool_name"), tool_result),
        )

        observation = {
            "tool_call": data,
            "tool_result": tool_result,
        }
        if not self._agent_keeps_turn_messages():
            # 无轮级消息状态的旧式 agent 仍需整段历史注入观察；轮级
            # 消息 agent 的历史已经活在追加式前缀里，重发只会击穿
            # provider 的前缀缓存。
            observation["execution_history"] = self._history_for_observation(
                execution_history
            )
        if budget_notice:
            observation["budget_notice"] = budget_notice
        execution_history.append(
            {
                "tool_call": data,
                "tool_result": tool_result,
            }
        )

        if self._tool_loop_was_stopped(tool_result):
            raise RunStoppedError(
                self._tool_loop_stopped_message(tool_result),
                kind="tool",
                stage="tool_call",
                error_type="loop_stopped",
            )

        tool_recovery = None
        terminal_delivery = self._tool_result_is_terminal_delivery(tool_result)
        if terminal_delivery:
            trace.record(
                "document_delivery_terminal",
                {
                    "version": tool_result.get("version"),
                    "published_path": tool_result.get("published_path"),
                },
            )
        expected_followup = self._tool_result_is_expected_followup(tool_result)
        tool_failed = self._tool_result_failed(tool_result) and not expected_followup
        if tool_failed:
            # approval_denied 不在停机名单里：审批拒绝作为普通工具失败
            # 回喂模型改道，绝不丢弃整轮进度。
            error_type = tool_result.get("error_type", "tool_error")
            if error_type == "permission_error":
                raise RunStoppedError(
                    self._tool_failure_message(tool_result),
                    kind="tool",
                    stage="tool_call",
                    error_type=error_type,
                )
            tool_recovery = self._reserve_recovery(
                kind="tool_feedback",
                stage="tool_observation",
                error_type=error_type,
                error=self._tool_failure_message(tool_result),
                trace=trace,
                state_store=state_store,
                process_entries=process_entries,
                recovery=recovery,
            )
        else:
            # Tool-feedback recovery is a consecutive-failure budget. Once the
            # model has corrected the call and a tool succeeds, early mistakes
            # must not consume retries needed for a later protocol/provider issue.
            recovery.reset("tool_feedback")

        # 逐步追加 JSONL 步进记录（O(1) 追加写），供断点续跑重建历史；
        # checkpoint 本体只在阶段边界写，避免每步全量重写 state.json。
        state_store.append_step(
            self._build_step_record(len(execution_history) - 1, data, tool_result)
        )

        final_response = self._call_model_with_recovery(
            lambda: self.agent.run_with_observation(user_input, observation),
            stage="tool_observation",
            trace=trace,
            state_store=state_store,
            process_entries=process_entries,
            recovery=recovery,
        )
        trace.record("model_called")
        self._record_selected_skill(
            trace,
            recorded_selected_skill,
            process_entries,
        )

        final_response, preface, final_data = self._parse_with_protocol_recovery(
            response=final_response,
            allowed_types=(
                {"final_answer"}
                if terminal_delivery
                else FINAL_AFTER_TOOL_TYPES
            ),
            user_input=user_input,
            stage="tool_follow_up",
            trace=trace,
            state_store=state_store,
            process_entries=process_entries,
            recovery=recovery,
            execution_history=execution_history,
        )
        if final_data is None:
            return final_response

        if tool_recovery is not None:
            self._record_recovery_succeeded(
                tool_recovery,
                trace=trace,
                state_store=state_store,
                recovery=recovery,
            )

        self._emit_process_entry(
            trace,
            process_entries,
            assistant_step_entry(preface),
        )

        if final_data["type"] != "final_answer":
            return final_response

        return final_data.get("content", "")

    def _verify_with_recovery(
        self,
        *,
        user_input,
        response,
        execution_history,
        trace,
        state_store,
        process_entries,
        recovery,
    ):
        verification = self.verification_gate.verify_final_output(
            response,
            execution_history=execution_history,
        )
        revise = getattr(self.agent, "run_with_verification_feedback", None)
        if verification["passed"] or not callable(revise):
            return response, verification

        while not verification["passed"]:
            try:
                retry_info = self._reserve_recovery(
                    kind="verification",
                    stage="final_verification",
                    error_type="verification_failed",
                    error=self._verification_error_summary(verification),
                    trace=trace,
                    state_store=state_store,
                    process_entries=process_entries,
                    recovery=recovery,
                )
            except RunStoppedError:
                return self._append_verification_failure(response, verification), verification

            revised = self._call_model_with_recovery(
                lambda: revise(
                    user_input,
                    response,
                    verification,
                    execution_history=self._history_for_observation(execution_history),
                ),
                stage="verification_revision",
                trace=trace,
                state_store=state_store,
                process_entries=process_entries,
                recovery=recovery,
            )
            revised, _preface, data = self._parse_with_protocol_recovery(
                response=revised,
                allowed_types={"final_answer"},
                user_input=user_input,
                stage="verification_revision",
                trace=trace,
                state_store=state_store,
                process_entries=process_entries,
                recovery=recovery,
                execution_history=execution_history,
            )
            if data is not None:
                response = data.get("content", "")
            else:
                response = revised
            verification = self.verification_gate.verify_final_output(
                response,
                execution_history=execution_history,
            )
            if verification["passed"]:
                self._record_recovery_succeeded(
                    retry_info,
                    trace=trace,
                    state_store=state_store,
                    recovery=recovery,
                )

        return response, verification

    def _verification_error_summary(self, verification):
        messages = [
            str(check.get("message", "")).strip()
            for check in (verification or {}).get("checks", [])
            if not check.get("passed") and check.get("message")
        ]
        return "; ".join(messages) or "Final output verification failed"

    def _append_verification_failure(self, response, verification):
        content = str(response or "").strip()
        reason = self._verification_error_summary(verification)
        suffix = f"任务未能完整完成：最终回答验证未通过。原因：{reason}"
        return f"{content}\n\n---\n\n{suffix}" if content else suffix

    def _record_selected_skill(self, trace, recorded_selected_skill, process_entries):
        context_getter = getattr(self.agent, "current_turn_tool_context", None)
        if not callable(context_getter):
            return

        tool_context = context_getter() or {}
        selected_skill = tool_context.get("selected_skill")
        if not selected_skill or selected_skill in recorded_selected_skill:
            return

        recorded_selected_skill.add(selected_skill)
        trace.record(
            "skill_selected",
            {
                "selected_skill": selected_skill,
                "available_tools": list(tool_context.get("available_tools") or []),
                "plain_answer": bool(tool_context.get("plain_answer")),
            },
        )
        self._emit_process_entry(
            trace,
            process_entries,
            assistant_step_entry(f"我将使用 {selected_skill} 进行处理。"),
        )

    def _effective_allowed_tools(self, trace):
        configured_enabled = set(self.allowed_tools)
        registered = set(getattr(self.tool_registry, "tools", {}).keys()) if self.tool_registry else set()
        context_getter = getattr(self.agent, "current_turn_tool_context", None)

        if callable(context_getter):
            tool_context = context_getter()
            selected_skill = tool_context.get("selected_skill")
            plain_answer = bool(tool_context.get("plain_answer"))
        else:
            selected_skill = None
            plain_answer = False

        for missing_tool in sorted(configured_enabled - registered):
            trace.record(
                "enabled_tool_missing",
                {
                    "tool_name": missing_tool,
                },
            )

        effective = sorted(configured_enabled & registered)

        trace.record(
            "effective_allowed_tools",
            {
                "selected_skill": selected_skill,
                "plain_answer": plain_answer,
                "enabled_tools": effective,
            },
        )
        return effective

    def _is_tool_call_json(self, text):
        try:
            _preface, data = extract_model_json(text)
        except InvalidModelJSONError:
            return False

        return data.get("type") == "tool_call"

    def _looks_like_tool_call_response(self, text):
        stripped = str(text or "").strip()
        if not stripped:
            return True

        return '"type"' in stripped and "tool_call" in stripped

    def _tool_loop_was_stopped(self, tool_result):
        return (
            isinstance(tool_result, dict)
            and tool_result.get("ok") is False
            and tool_result.get("error_type") == "loop_stopped"
        )

    def _tool_result_failed(self, tool_result):
        return isinstance(tool_result, dict) and tool_result.get("ok") is False

    def _tool_result_is_expected_followup(self, tool_result):
        if not isinstance(tool_result, dict) or tool_result.get("ok") is not False:
            return False
        if tool_result.get("terminal") is True:
            return True
        if tool_result.get("requires_user_input") is True:
            return True
        return str(tool_result.get("error") or "") == "DOCX_QA_BLOCKED"

    @staticmethod
    def _tool_result_is_terminal_delivery(tool_result):
        return bool(
            isinstance(tool_result, dict)
            and tool_result.get("ok") is True
            and tool_result.get("terminal") is True
            and tool_result.get("workflow_complete") is True
            and tool_result.get("published_path")
        )

    @staticmethod
    def _terminal_delivery_final(execution_history):
        result = {}
        for item in reversed(list(execution_history or [])):
            candidate = (item or {}).get("tool_result")
            if (
                isinstance(candidate, dict)
                and candidate.get("workflow_complete") is True
                and candidate.get("published_path")
            ):
                result = candidate
                break
        version = result.get("version")
        version_text = f"v{int(version):03d}" if version is not None else "已发布版本"
        warning_count = int(result.get("warning_count") or 0)
        warning_text = (
            f"；仍有 {warning_count} 条非阻塞 warning，详见 QA 报告"
            if warning_count
            else ""
        )
        return (
            f"文档已完成完整 QA 并发布（{version_text}）："
            f"{result.get('published_path')}{warning_text}。"
        )

    def _tool_failure_message(self, tool_result):
        tool_name = str(tool_result.get("tool_name") or "tool")
        error = str(
            tool_result.get("error_message")
            or tool_result.get("error")
            or tool_result.get("message")
            or tool_result.get("reason")
            or "工具执行失败"
        ).strip()
        return f"{tool_name}: {error}"

    def _tool_loop_stopped_message(self, tool_result):
        error = str(
            tool_result.get("error")
            or tool_result.get("error_message")
            or "工具调用循环已停止。"
        ).strip()
        tool_name = str(tool_result.get("tool_name") or "tool")

        if error.startswith("Repeated tool call blocked:"):
            return (
                "检测到重复工具调用，已停止继续执行。"
                f"工具：{tool_name}。原因：{error}"
            )

        if error.startswith("Maximum tool calls exceeded:"):
            return f"工具调用达到上限，已停止继续执行。原因：{error}"

        return f"工具调用循环已停止。工具：{tool_name}。原因：{error}"

    def _agent_keeps_turn_messages(self):
        active = getattr(self.agent, "turn_messages_active", None)
        return callable(active) and bool(active())

    def _history_for_observation(self, execution_history):
        if not execution_history:
            return []

        budget = TokenBudget(max_tokens=max(1, self.context_limit // 2))
        selected = []

        # Newer raw results are more useful for the next decision. Older entries
        # retain their call identity and a bounded result summary.
        for item in reversed(execution_history):
            serialized = json.dumps(item, ensure_ascii=False, sort_keys=True)
            estimated = budget.estimate(serialized)
            if estimated <= budget.remaining_tokens:
                entry = item
                budget.add("execution_history", serialized)
            else:
                entry = self._compact_history_entry(item)
                budget.add(
                    "execution_history",
                    json.dumps(entry, ensure_ascii=False, sort_keys=True),
                )
            selected.append(entry)

        selected.reverse()
        return selected

    def _compact_history_entry(self, item):
        tool_call = dict(item.get("tool_call") or {})
        tool_result = item.get("tool_result")
        tool_name = str(tool_call.get("tool_name") or "tool")
        compact_result = {
            "ok": not (
                isinstance(tool_result, dict)
                and tool_result.get("ok") is False
            ),
            "summary": summarize_tool_result(tool_name, tool_result),
            "compacted": True,
        }
        if isinstance(tool_result, dict) and tool_result.get("error_type"):
            compact_result["error_type"] = tool_result["error_type"]

        return {
            "tool_call": {
                "tool_name": tool_name,
                "arguments": dict(tool_call.get("arguments") or {}),
                "reason": tool_call.get("reason", ""),
            },
            "tool_result": compact_result,
        }

    def _new_tool_policy(self):
        if self.tool_policy is None:
            return ToolExecutionPolicy()

        return replace(
            self.tool_policy,
            call_count=0,
            repeated_calls={},
            last_call_key="",
            consecutive_repeated_calls=0,
        )

    def _finalize_run(
        self,
        *,
        context,
        user_input,
        response,
        verification,
        execution_history,
        process_entries,
        trace,
        state_store,
        writer,
        run_analytics,
        usage_baseline=None,
    ):
        writer.write_final_output(response)
        writer.write_verification(verification)
        writer.write_artifacts(execution_history)
        if run_analytics is not None:
            run_analytics.record_final_output(response)
            run_analytics.record_verification(verification)
        self._remember_completed_turn(user_input, response, process_entries)
        trace.record("run_finished")
        status = "finished" if verification["passed"] else "failed"
        if run_analytics is not None:
            self._record_run_token_usage(run_analytics, usage_baseline)
            run_analytics.finish(status)
        state_store.save_checkpoint(
            "run_finished",
            status,
            {"verification": verification},
        )
        run_result = RunResult(
            response,
            status=status,
            run_id=context.run_id,
            run_dir=context.outputs_dir,
            verification=verification,
            artifacts=self._collect_artifacts(execution_history),
        )
        trace.record(
            "run_completed",
            {
                "status": run_result.status,
                "run_id": run_result.run_id,
                "result": run_result,
            },
        )
        trace.save()
        self.last_trace_events = list(trace.events)
        return run_result

    def _collect_artifacts(self, execution_history):
        artifacts = []
        for entry in execution_history or []:
            tool_name = (entry.get("tool_call") or {}).get("tool_name", "")
            result = entry.get("tool_result")
            if not isinstance(result, dict):
                continue
            for path in result.get("artifacts", []):
                artifacts.append({"tool": tool_name, "path": str(path)})
        return artifacts

    def _build_step_record(self, index, tool_call, tool_result):
        artifacts = []
        if isinstance(tool_result, dict):
            artifacts = [str(path) for path in tool_result.get("artifacts", [])]
        return {
            "index": index,
            "tool_call": tool_call,
            "tool_result": self._step_result_snapshot(tool_call, tool_result),
            "artifacts": artifacts,
        }

    def _step_result_snapshot(self, tool_call, tool_result):
        try:
            serialized = json.dumps(tool_result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            serialized = None
        if serialized is not None and len(serialized) <= STEP_RESULT_SNAPSHOT_LIMIT:
            return tool_result
        return self._compact_history_entry(
            {"tool_call": tool_call, "tool_result": tool_result}
        )["tool_result"]

    def _finish_stopped_run(
        self,
        *,
        user_input,
        error,
        process_entries,
        trace,
        state_store,
        writer,
        run_analytics,
        execution_history=None,
        usage_baseline=None,
    ):
        response = self._build_partial_failure_output(error, process_entries)
        verification = {
            "passed": False,
            "checks": [
                {
                    "name": "run_recovery_completed",
                    "passed": False,
                    "message": str(error),
                    "kind": error.kind,
                    "stage": error.stage,
                    "error_type": error.error_type,
                    "exhausted": error.exhausted,
                }
            ],
        }
        details = {
            "status": "failed",
            "kind": error.kind,
            "stage": error.stage,
            "error_type": error.error_type,
            "error": str(error),
            "exhausted": error.exhausted,
            "verification": verification,
        }
        trace.record("run_stopped", details)
        writer.write_final_output(response)
        writer.write_verification(verification)
        writer.write_artifacts(execution_history or [])
        self._remember_completed_turn(user_input, response, process_entries)
        if run_analytics is not None:
            run_analytics.record_final_output(response)
            run_analytics.record_verification(verification)
            self._record_run_token_usage(run_analytics, usage_baseline)
            run_analytics.finish(
                "failed",
                error_type=error.error_type,
                error_message=str(error),
            )
        trace.record("run_finished", {"status": "failed"})
        state_store.save_checkpoint("run_finished", "failed", details)
        run_result = RunResult(
            response,
            status="stopped",
            run_id=trace.context.run_id,
            run_dir=trace.context.outputs_dir,
            verification=verification,
            stop_reason={
                "kind": error.kind,
                "stage": error.stage,
                "error_type": error.error_type,
                "error": str(error),
                "exhausted": error.exhausted,
            },
            artifacts=self._collect_artifacts(execution_history or []),
        )
        trace.record(
            "run_completed",
            {
                "status": run_result.status,
                "run_id": run_result.run_id,
                "result": run_result,
            },
        )
        trace.save()
        self.last_trace_events = list(trace.events)
        return run_result

    def _build_partial_failure_output(self, error, process_entries):
        completed = []
        for entry in process_entries or []:
            if entry.get("type") != "tool_result":
                continue
            summary = str(entry.get("summary") or "").strip()
            if summary and summary not in completed:
                completed.append(summary)

        lines = [
            "任务未能完整完成。",
            "",
            f"停止原因：{error}",
        ]
        if completed:
            lines.extend(["", "已完成步骤："])
            lines.extend(f"- {summary}" for summary in completed)
        lines.extend(
            [
                "",
                "运行状态已标记为 failed；可以根据上述停止原因继续重试。",
            ]
        )
        return "\n".join(lines)

    def _record_run_failed(self, trace, state_store, exc):
        details = {
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        trace.record("run_failed", details)
        state_store.save_checkpoint("run_failed", "failed", details)
        trace.save()
        self.last_trace_events = list(trace.events)


ResearchAgentHarness = YCAgentRuntime
