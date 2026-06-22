from yc_agents.harness.context import RunContext
from yc_agents.harness.trace import TraceRecorder
from yc_agents.harness.run_outputs import RunOutputWriter
from yc_agents.harness.json_protocol import InvalidModelJSONError, parse_model_json
from yc_agents.harness.state import StateStore
from yc_agents.harness.tool_gateway import ToolGateway
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
    ):
        self.agent = agent
        self.expects_json = expects_json
        self.tool_registry = tool_registry
        self.allowed_tools = allowed_tools or []
        self.approval_gate = approval_gate
        self.verification_gate = verification_gate or VerificationGate()

    def run(self, user_input, controller=None):
        user_input = self._apply_redirects(user_input, controller)
        context = RunContext(user_input=user_input)
        trace = TraceRecorder(context)
        writer = RunOutputWriter(context)
        state_store = StateStore(context.outputs_dir / "state.json")

        self._check_controller(controller, "run_started", trace)
        trace.record("run_started")
        state_store.save_checkpoint("run_started", "running")
        writer.write_input()
        writer.write_context(self._build_context_snapshot(context))

        self._check_controller(controller, "before_model_call", trace)
        response = self.agent.run(user_input)
        trace.record("model_called")
        state_store.save_checkpoint("model_called", "running")

        if self.expects_json:
            response = self._handle_json_response(trace, user_input, response, controller)

        self._check_controller(controller, "before_final_write", trace)
        response = self._handle_redirect_before_final_write(
            trace,
            user_input,
            response,
            controller,
        )
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

    def _handle_json_response(self, trace, user_input, response, controller=None):
        try:
            data = parse_model_json(response)
        except InvalidModelJSONError as exc:
            trace.record("invalid_model_json", {"error": str(exc), "raw_text": exc.raw_text})
            return response

        if data["type"] == "tool_call":
            return self._handle_tool_call(trace, user_input, data, controller)

        if data["type"] == "final_answer":
            return data.get("content", "")

        if data["type"] == "skill_selection":
            trace.record("skill_selected", {
                "selected_skill": data.get("selected_skill"),
                "confidence": data.get("confidence"),
                "reason": data.get("reason"),
            })

        return response

    def _handle_tool_call(self, trace, user_input, data, controller=None):
        trace.record("tool_call_requested", data)
        self._check_controller(controller, "before_tool_call", trace)

        gateway = ToolGateway(
            tool_registry=self.tool_registry,
            allowed_tools=self.allowed_tools,
            trace=trace,
            approval_gate=self.approval_gate,
        )

        tool_result = gateway.run_tool(
            data["tool_name"],
            **data["arguments"],
        )
        self._check_controller(controller, "after_tool_call", trace)

        observation = {
            "tool_call": data,
            "tool_result": tool_result,
        }

        user_input = self._apply_redirects(user_input, controller)
        self._check_controller(controller, "before_model_call", trace)
        final_response = self.agent.run_with_observation(user_input, observation)
        trace.record("model_called")

        final_data = parse_model_json(final_response)

        if final_data["type"] != "final_answer":
            return final_response

        return final_data.get("content", "")

    def _apply_redirects(self, user_input, controller=None):
        if controller is None or not hasattr(controller, "pop_redirects"):
            return user_input

        redirects = controller.pop_redirects()
        if not redirects:
            return user_input

        return f"{user_input}\n\n用户中途改方向：\n" + "\n".join(redirects)

    def _handle_redirect_before_final_write(
        self,
        trace,
        user_input,
        response,
        controller=None,
    ):
        if controller is None:
            return response

        redirected_input = self._apply_redirects(user_input, controller)
        if redirected_input == user_input:
            return response

        trace.record("redirect_applied", {"checkpoint": "before_final_write"})
        self._check_controller(controller, "before_model_call", trace)
        redirected_response = self.agent.run(redirected_input)
        trace.record("model_called")

        if self.expects_json:
            return self._handle_json_response(
                trace,
                redirected_input,
                redirected_response,
                controller,
            )

        return redirected_response

    def _check_controller(self, controller, checkpoint, trace):
        if controller is None:
            return

        wait_if_paused = getattr(controller, "wait_if_paused", None)
        if wait_if_paused is not None:
            wait_if_paused()

        raise_if_cancelled = getattr(controller, "raise_if_cancelled", None)
        if raise_if_cancelled is not None:
            try:
                raise_if_cancelled(checkpoint)
            except Exception:
                trace.record("run_cancelled", {"checkpoint": checkpoint})
                trace.save()
                raise
            return

        if getattr(controller, "cancelled", False):
            trace.record("run_cancelled", {"checkpoint": checkpoint})
            trace.save()
            raise RuntimeError("Run cancelled")


ResearchAgentHarness = YCAgentRuntime
