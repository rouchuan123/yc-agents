from yc_agents.harness.context import RunContext
from yc_agents.harness.trace import TraceRecorder
from yc_agents.harness.run_outputs import RunOutputWriter
from yc_agents.harness.json_protocol import (
    InvalidModelJSONError,
    parse_model_json,
)


class YCAgentRuntime:
    def __init__(self, agent, expects_json=False):
        self.agent = agent
        self.expects_json = expects_json

    def run(self, user_input):
        context = RunContext(user_input=user_input)
        trace = TraceRecorder(context)
        writer = RunOutputWriter(context)

        trace.record("run_started")
        writer.write_input()

        response = self.agent.run(user_input)

        trace.record("model_called")

        if self.expects_json:
            self._record_json_decision(trace, response)

        writer.write_final_output(response)

        trace.record("run_finished")
        trace.save()

        return response

    def _record_json_decision(self, trace, response):
        try:
            data = parse_model_json(response)
        except InvalidModelJSONError as exc:
            trace.record(
                "invalid_model_json",
                {
                    "error": str(exc),
                    "raw_text": exc.raw_text,
                },
            )
            return

        if data["type"] == "skill_selection":
            trace.record(
                "skill_selected",
                {
                    "selected_skill": data.get("selected_skill"),
                    "confidence": data.get("confidence"),
                    "reason": data.get("reason"),
                },
            )


ResearchAgentHarness = YCAgentRuntime