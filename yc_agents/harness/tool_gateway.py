class ToolNotAllowedError(PermissionError):
    pass


class ToolGateway:
    def __init__(self, tool_registry, allowed_tools=None, trace=None):
        self.tool_registry = tool_registry
        self.allowed_tools = set(allowed_tools or [])
        self.trace = trace

    def run_tool(self, name, *args, **kwargs):
        if name not in self.allowed_tools:
            self._record(
                "tool_denied",
                {
                    "tool_name": name,
                    "reason": "Tool is not allowed for this run",
                },
            )
            raise ToolNotAllowedError(f"Tool is not allowed: {name}")

        try:
            result = self.tool_registry.run_tool(name, *args, **kwargs)
        except Exception as exc:
            self._record(
                "tool_failed",
                {
                    "tool_name": name,
                    "error": str(exc),
                },
            )
            raise

        self._record(
            "tool_called",
            {
                "tool_name": name,
                "result": result,
            },
        )
        return result

    def _record(self, event_type, payload):
        if self.trace is None:
            return

        self.trace.record(event_type, payload)