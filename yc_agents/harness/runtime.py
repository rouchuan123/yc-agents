from dataclasses import replace

from yc_agents.harness.context import RunContext
from yc_agents.harness.trace import TraceRecorder
from yc_agents.harness.run_outputs import RunOutputWriter
from yc_agents.harness.json_protocol import InvalidModelJSONError, parse_model_json
from yc_agents.harness.state import StateStore
from yc_agents.harness.tool_gateway import ToolGateway
from yc_agents.harness.tool_policy import ToolExecutionPolicy
from yc_agents.harness.verification import VerificationGate


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

    def run(self, user_input):
        context = RunContext(user_input=user_input, output_root=self.output_root)
        trace = TraceRecorder(context, event_callback=self.event_callback)
        writer = RunOutputWriter(context)
        state_store = StateStore(context.outputs_dir / "state.json")

        try:
            trace.record("run_started")
            state_store.save_checkpoint("run_started", "running", {"user_input": user_input})
            writer.write_input()
            writer.write_context(self._build_context_snapshot(context))

            response = self.agent.run(user_input)
            trace.record("model_called")
            state_store.save_checkpoint("model_called", "running")

            if self.expects_json:
                response = self._handle_json_response(trace, user_input, response)

            writer.write_final_output(response)
            verification = self.verification_gate.verify_final_output(response)
            writer.write_verification(verification)
            self._remember_turn(user_input, response)
            trace.record("run_finished")
            state_store.save_checkpoint(
                "run_finished",
                "finished" if verification["passed"] else "failed",
                {"verification": verification},
            )
            trace.save()

            return response
        except Exception as exc:
            self._record_run_failed(trace, state_store, exc)
            raise

    def stream(self, user_input):
        stream_agent = getattr(self.agent, "stream", None)

        if not callable(stream_agent):
            yield self.run(user_input)
            return

        context = RunContext(user_input=user_input, output_root=self.output_root)
        trace = TraceRecorder(context, event_callback=self.event_callback)
        writer = RunOutputWriter(context)
        state_store = StateStore(context.outputs_dir / "state.json")

        try:
            trace.record("run_started")
            state_store.save_checkpoint("run_started", "running", {"user_input": user_input})
            writer.write_input()
            writer.write_context(self._build_context_snapshot(context))

            chunks = []
            buffered_for_json = self.expects_json
            first_chunk_seen = False

            for chunk in stream_agent(user_input):
                if chunk is None:
                    continue

                text = str(chunk)

                if not text:
                    continue

                chunks.append(text)

                if not buffered_for_json:
                    yield text
                    continue

                if not first_chunk_seen:
                    if not text.strip():
                        continue

                    first_chunk_seen = True

                    if not text.lstrip().startswith("{"):
                        buffered_for_json = False
                        yield text

            response = "".join(chunks)
            trace.record("model_called")
            state_store.save_checkpoint("model_called", "running")

            if self.expects_json and buffered_for_json:
                response = self._handle_json_response(trace, user_input, response)
                yield response

            writer.write_final_output(response)
            verification = self.verification_gate.verify_final_output(response)
            writer.write_verification(verification)
            self._remember_turn(user_input, response)
            trace.record("run_finished")
            state_store.save_checkpoint(
                "run_finished",
                "finished" if verification["passed"] else "failed",
                {"verification": verification},
            )
            trace.save()
        except Exception as exc:
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

    def _handle_json_response(self, trace, user_input, response):
        policy = self._new_tool_policy()

        while True:
            response = self._handle_json_response_once(
                trace,
                user_input,
                response,
                policy,
            )

            if not self._is_tool_call_json(response):
                return response

    def _handle_json_response_once(self, trace, user_input, response, policy):
        try:
            data = parse_model_json(response)
        except InvalidModelJSONError as exc:
            trace.record("invalid_model_json", {"error": str(exc), "raw_text": exc.raw_text})
            return response

        if data["type"] == "tool_call":
            return self._handle_tool_call(trace, user_input, data, policy)

        if data["type"] == "final_answer":
            return data.get("content", "")

        if data["type"] == "skill_selection":
            trace.record("skill_selected", {
                "selected_skill": data.get("selected_skill"),
                "confidence": data.get("confidence"),
                "reason": data.get("reason"),
            })

        return response

    def _handle_tool_call(self, trace, user_input, data, policy):
        trace.record("tool_call_requested", data)

        gateway = ToolGateway(
            tool_registry=self.tool_registry,
            allowed_tools=self.allowed_tools,
            trace=trace,
            approval_gate=self.approval_gate,
            policy=policy,
        )

        tool_result = gateway.run_tool(
            data["tool_name"],
            **data["arguments"],
        )

        observation = {
            "tool_call": data,
            "tool_result": tool_result,
        }

        if self._tool_loop_was_stopped(tool_result):
            return self._tool_loop_stopped_message(tool_result)

        final_response = self.agent.run_with_observation(user_input, observation)
        trace.record("model_called")

        try:
            final_data = parse_model_json(final_response)
        except InvalidModelJSONError as exc:
            trace.record("invalid_model_json", {"error": str(exc), "raw_text": exc.raw_text})
            return final_response

        if final_data["type"] != "final_answer":
            return final_response

        return final_data.get("content", "")

    def _is_tool_call_json(self, text):
        try:
            data = parse_model_json(text)
        except InvalidModelJSONError:
            return False

        return data.get("type") == "tool_call"

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


ResearchAgentHarness = YCAgentRuntime
