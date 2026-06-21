class GuardrailViolationError(RuntimeError):
    pass


class Guardrails:
    def __init__(self, max_steps=3, max_tool_calls=1):
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.steps = 0
        self.tool_calls = 0

    def record_step(self):
        self.steps += 1

        if self.steps > self.max_steps:
            raise GuardrailViolationError(
                f"Maximum steps exceeded: {self.steps}/{self.max_steps}"
            )

    def record_tool_call(self):
        self.tool_calls += 1

        if self.tool_calls > self.max_tool_calls:
            raise GuardrailViolationError(
                f"Maximum tool calls exceeded: "
                f"{self.tool_calls}/{self.max_tool_calls}"
            )