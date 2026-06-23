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

    def run(self, user_input):
        context = RunContext(user_input=user_input)
        trace = TraceRecorder(context)
        writer = RunOutputWriter(context)
        state_store = StateStore(context.outputs_dir / "state.json")

        trace.record("run_started")
        state_store.save_checkpoint("run_started", "running")
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
        try:
            data = parse_model_json(response)
        except InvalidModelJSONError as exc:
            trace.record("invalid_model_json", {"error": str(exc), "raw_text": exc.raw_text})
            return response

        if data["type"] == "tool_call":
            return self._handle_tool_call(trace, user_input, data)

        if data["type"] == "final_answer":
            return data.get("content", "")

        if data["type"] == "skill_selection":
            trace.record("skill_selected", {
                "selected_skill": data.get("selected_skill"),
                "confidence": data.get("confidence"),
                "reason": data.get("reason"),
            })

        return response

    def _handle_tool_call(self, trace, user_input, data):
        trace.record("tool_call_requested", data)

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

        observation = {
            "tool_call": data,
            "tool_result": tool_result,
        }

        final_response = self.agent.run_with_observation(user_input, observation)
        trace.record("model_called")

        final_data = parse_model_json(final_response)

        if final_data["type"] != "final_answer":
            return final_response

        return final_data.get("content", "")


ResearchAgentHarness = YCAgentRuntime
