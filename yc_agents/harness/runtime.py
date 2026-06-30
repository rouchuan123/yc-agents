from dataclasses import replace

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
    tool_call_entry,
    tool_result_entry,
)
from yc_agents.harness.state import StateStore
from yc_agents.harness.tool_gateway import ToolGateway
from yc_agents.harness.tool_policy import ToolExecutionPolicy
from yc_agents.harness.verification import VerificationGate


PLAIN_ANSWER_ALLOWED_TOOLS = ["workspace_files", "file_reader"]
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
        self.fail_on_invalid_json = fail_on_invalid_json
        self.context_limit = int(context_limit or 8000)
        if analytics_recorder is not None:
            self.managed_resources.append(analytics_recorder)
        self.last_trace_events = []
        self.last_run_id = None

    def run(self, user_input):
        context = RunContext(user_input=user_input, output_root=self.output_root)
        self.last_run_id = context.run_id
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

            response = self.agent.run(user_input)
            trace.record("model_called")
            self._record_selected_skill(trace, recorded_selected_skill)
            state_store.save_checkpoint("model_called", "running")

            if self.expects_json:
                response = self._handle_json_response(
                    trace,
                    user_input,
                    response,
                    recorded_selected_skill,
                    process_entries,
                )

            writer.write_final_output(response)
            verification = self.verification_gate.verify_final_output(response)
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

            chunks = []
            buffered_for_json = self.expects_json

            for chunk in stream_agent(user_input):
                if chunk is None:
                    continue

                text = str(chunk)

                if not text:
                    continue

                chunks.append(text)

                if not buffered_for_json:
                    yield text

            response = "".join(chunks)
            trace.record("model_called")
            self._record_selected_skill(trace, recorded_selected_skill)
            state_store.save_checkpoint("model_called", "running")

            if self.expects_json and buffered_for_json:
                response = self._handle_json_response(
                    trace,
                    user_input,
                    response,
                    recorded_selected_skill,
                    process_entries,
                )
                yield response

            writer.write_final_output(response)
            verification = self.verification_gate.verify_final_output(response)
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
            "allowed_tools": list(self.allowed_tools),
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
    ):
        policy = self._new_tool_policy()
        invalid_attempts = 0

        while True:
            response, invalid_error = self._handle_json_response_once(
                trace,
                user_input,
                response,
                policy,
                recorded_selected_skill,
                process_entries,
            )

            if invalid_error is not None:
                if invalid_attempts < self.invalid_json_retry_count:
                    invalid_attempts += 1
                    response = self._retry_after_invalid_json(
                        user_input,
                        invalid_error,
                        expectation=self._runtime_expectation(),
                    )
                    trace.record("model_called")
                    self._record_selected_skill(trace, recorded_selected_skill)
                    continue
                if self.fail_on_invalid_json:
                    raise invalid_error
                return response

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
    ):
        try:
            preface, data = extract_model_json(
                response,
                allowed_types=RUNTIME_RESPONSE_TYPES,
            )
        except InvalidModelJSONError as exc:
            trace.record("invalid_model_json", {"error": str(exc), "raw_text": exc.raw_text})
            return response, exc

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
            ), None

        if data["type"] == "final_answer":
            return data.get("content", ""), None

        return response, None

    def _runtime_expectation(self):
        return {"allowed_types": sorted(RUNTIME_RESPONSE_TYPES)}

    def _retry_after_invalid_json(self, user_input, error, expectation=None):
        retry = getattr(self.agent, "run_with_protocol_error", None)
        if callable(retry):
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

        tool_result = gateway.run_tool(
            data["tool_name"],
            **data["arguments"],
        )
        self._emit_process_entry(
            trace,
            process_entries,
            tool_result_entry(data.get("tool_name"), tool_result),
        )

        observation = {
            "tool_call": data,
            "tool_result": tool_result,
        }

        if self._tool_loop_was_stopped(tool_result):
            return self._tool_loop_stopped_message(tool_result)

        final_response = self.agent.run_with_observation(user_input, observation)
        trace.record("model_called")
        self._record_selected_skill(trace, recorded_selected_skill)

        try:
            preface, final_data = extract_model_json(
                final_response,
                allowed_types=FINAL_AFTER_TOOL_TYPES,
            )
        except InvalidModelJSONError as exc:
            trace.record("invalid_model_json", {"error": str(exc), "raw_text": exc.raw_text})
            if self.fail_on_invalid_json:
                raise exc
            self._emit_process_entry(
                trace,
                process_entries,
                assistant_step_entry(final_response),
            )
            return final_response

        self._emit_process_entry(
            trace,
            process_entries,
            assistant_step_entry(preface),
        )

        if final_data["type"] != "final_answer":
            return final_response

        return final_data.get("content", "")

    def _record_selected_skill(self, trace, recorded_selected_skill):
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
                "allowed_tools": list(tool_context.get("allowed_tools") or []),
                "plain_answer": bool(tool_context.get("plain_answer")),
            },
        )

    def _effective_allowed_tools(self, trace):
        runtime_allowed = set(self.allowed_tools)
        registered = set(getattr(self.tool_registry, "tools", {}).keys()) if self.tool_registry else set()
        context_getter = getattr(self.agent, "current_turn_tool_context", None)

        if callable(context_getter):
            tool_context = context_getter()
            declared = set(tool_context.get("allowed_tools") or PLAIN_ANSWER_ALLOWED_TOOLS)
            selected_skill = tool_context.get("selected_skill")
            plain_answer = bool(tool_context.get("plain_answer"))
        else:
            declared = set(self.allowed_tools)
            selected_skill = None
            plain_answer = False

        for missing_tool in sorted(declared - registered):
            trace.record(
                "skill_allowed_tool_missing",
                {
                    "selected_skill": selected_skill,
                    "tool_name": missing_tool,
                },
            )

        effective = sorted(runtime_allowed & declared)
        if registered:
            effective = sorted(set(effective) & registered)

        trace.record(
            "effective_allowed_tools",
            {
                "selected_skill": selected_skill,
                "plain_answer": plain_answer,
                "allowed_tools": effective,
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

    def _tool_loop_stopped_message(self, tool_result):
        error = tool_result.get("error") or "工具调用循环已停止。"
        return f"工具调用次数过多，已停止继续执行。原因：{error}"

    def _new_tool_policy(self):
        if self.tool_policy is None:
            return ToolExecutionPolicy()

        return replace(self.tool_policy, call_count=0, repeated_calls={})

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
