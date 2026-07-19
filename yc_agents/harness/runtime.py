import json
import time
from dataclasses import replace

from yc_agents.core.exceptions import LLMCallError
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
from yc_agents.harness.token_budget import TokenBudget
from yc_agents.harness.verification import VerificationGate


RUNTIME_RESPONSE_TYPES = {"tool_call", "final_answer"}
FINAL_AFTER_TOOL_TYPES = {"tool_call", "final_answer"}


class YCAgentRuntime:
    def __init__(
        self,
        agent,
        expects_json=False,
        tool_registry=None,
        allowed_tools=None,
        approval_gate=None,
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
    ):
        self.agent = agent
        self.expects_json = expects_json
        self.tool_registry = tool_registry
        self.allowed_tools = allowed_tools or []
        self.approval_gate = approval_gate
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

            response = self._call_model_with_recovery(
                lambda: self.agent.run(user_input),
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
                response = self._handle_json_response(
                    trace,
                    user_input,
                    response,
                    recorded_selected_skill,
                    process_entries,
                    execution_history,
                    recovery,
                    state_store,
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
            writer.write_final_output(response)
            writer.write_verification(verification)
            if run_analytics is not None:
                run_analytics.record_final_output(response)
                run_analytics.record_verification(verification)
            self._remember_completed_turn(user_input, response, process_entries)
            trace.record("run_finished")
            if run_analytics is not None:
                run_analytics.finish(
                    "finished" if verification["passed"] else "failed"
                )
            state_store.save_checkpoint(
                "run_finished",
                "finished" if verification["passed"] else "failed",
                {"verification": verification},
            )
            trace.save()
            self.last_trace_events = list(trace.events)

            return response
        except RunStoppedError as exc:
            return self._finish_stopped_run(
                user_input=user_input,
                error=exc,
                process_entries=process_entries,
                trace=trace,
                state_store=state_store,
                writer=writer,
                run_analytics=run_analytics,
            )
        except Exception as exc:
            if run_analytics is not None:
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
                response = self._handle_json_response(
                    trace,
                    user_input,
                    response,
                    recorded_selected_skill,
                    process_entries,
                    execution_history,
                    recovery,
                    state_store,
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
                yield response
            else:
                verification = self.verification_gate.verify_final_output(response)
            writer.write_final_output(response)
            writer.write_verification(verification)
            if run_analytics is not None:
                run_analytics.record_final_output(response)
                run_analytics.record_verification(verification)
            self._remember_completed_turn(user_input, response, process_entries)
            trace.record("run_finished")
            if run_analytics is not None:
                run_analytics.finish(
                    "finished" if verification["passed"] else "failed"
                )
            state_store.save_checkpoint(
                "run_finished",
                "finished" if verification["passed"] else "failed",
                {"verification": verification},
            )
            trace.save()
            self.last_trace_events = list(trace.events)
        except RunStoppedError as exc:
            response = self._finish_stopped_run(
                user_input=user_input,
                error=exc,
                process_entries=process_entries,
                trace=trace,
                state_store=state_store,
                writer=writer,
                run_analytics=run_analytics,
            )
            yield response
        except Exception as exc:
            if run_analytics is not None:
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

        details = checkpoint.get("details", {})
        user_input = details.get("user_input")

        if not user_input:
            return "Checkpoint does not contain user input; cannot resume safely."

        if redirect_instruction:
            user_input = f"{user_input}\n\n用户追加指令：{redirect_instruction}"

        return self.run(user_input)

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
            execution_history=self._history_for_observation(execution_history),
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
        while True:
            try:
                result = callback()
            except LLMCallError as exc:
                if not exc.retryable:
                    raise RunStoppedError(
                        str(exc),
                        kind="provider",
                        stage=stage,
                        error_type=exc.cause_type or exc.__class__.__name__,
                    ) from exc
                retry_info = self._reserve_recovery(
                    kind="provider",
                    stage=stage,
                    error_type=exc.cause_type or exc.__class__.__name__,
                    error=str(exc),
                    trace=trace,
                    state_store=state_store,
                    process_entries=process_entries,
                    recovery=recovery,
                )
                delay = max(
                    0.0,
                    float(self.recovery_policy.provider_backoff_seconds),
                ) * retry_info["attempt"]
                if delay:
                    time.sleep(delay)
                continue

            if retry_info is not None:
                self._record_recovery_succeeded(
                    retry_info,
                    trace=trace,
                    state_store=state_store,
                )
            return result

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
                        execution_history=execution_history,
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
            trace.record("recovery_exhausted", details)
            state_store.save_checkpoint("recovery_exhausted", "failed", details)
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

    def _record_recovery_succeeded(self, info, *, trace, state_store):
        trace.record("recovery_succeeded", dict(info))
        state_store.save_checkpoint("recovery_succeeded", "running", dict(info))

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
    ):
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
            "execution_history": self._history_for_observation(execution_history),
        }
        execution_history.append(
            {
                "tool_call": data,
                "tool_result": tool_result,
            }
        )

        if (
            isinstance(tool_result, dict)
            and tool_result.get("needs_approval")
            and not tool_result.get("allowed")
        ):
            raise RunStoppedError(
                self._tool_failure_message(tool_result),
                kind="tool",
                stage="tool_call",
                error_type="approval_required",
            )

        if self._tool_loop_was_stopped(tool_result):
            raise RunStoppedError(
                self._tool_loop_stopped_message(tool_result),
                kind="tool",
                stage="tool_call",
                error_type="loop_stopped",
            )

        tool_recovery = None
        if self._tool_result_failed(tool_result):
            error_type = tool_result.get("error_type", "tool_error")
            if error_type in {"permission_error", "approval_denied"}:
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
            allowed_types=FINAL_AFTER_TOOL_TYPES,
            user_input=user_input,
            stage="tool_follow_up",
            trace=trace,
            state_store=state_store,
            process_entries=process_entries,
            recovery=recovery,
            execution_history=self._history_for_observation(execution_history),
        )
        if final_data is None:
            return final_response

        if tool_recovery is not None:
            self._record_recovery_succeeded(
                tool_recovery,
                trace=trace,
                state_store=state_store,
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
        verification = self.verification_gate.verify_final_output(response)
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
                execution_history=self._history_for_observation(execution_history),
            )
            if data is not None:
                response = data.get("content", "")
            else:
                response = revised
            verification = self.verification_gate.verify_final_output(response)
            if verification["passed"]:
                self._record_recovery_succeeded(
                    retry_info,
                    trace=trace,
                    state_store=state_store,
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

        return replace(self.tool_policy, call_count=0, repeated_calls={})

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
        self._remember_completed_turn(user_input, response, process_entries)
        if run_analytics is not None:
            run_analytics.record_final_output(response)
            run_analytics.record_verification(verification)
            run_analytics.finish(
                "failed",
                error_type=error.error_type,
                error_message=str(error),
            )
        trace.record("run_finished", {"status": "failed"})
        state_store.save_checkpoint("run_finished", "failed", details)
        trace.save()
        self.last_trace_events = list(trace.events)
        return response

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
