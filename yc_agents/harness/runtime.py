from yc_agents.harness.context import RunContext
from yc_agents.harness.trace import TraceRecorder
from yc_agents.harness.run_outputs import RunOutputWriter


class ResearchAgentHarness:
    def __init__(self, agent):
        self.agent = agent

    def run(self, user_input):
        context = RunContext(user_input=user_input)
        trace = TraceRecorder(context)
        writer = RunOutputWriter(context)

        trace.record("run_started")
        writer.write_input()

        response = self.agent.run(user_input)

        trace.record("model_called")
        writer.write_final_output(response)

        trace.record("run_finished")
        trace.save()

        return response