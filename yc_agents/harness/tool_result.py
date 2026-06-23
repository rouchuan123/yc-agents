from dataclasses import dataclass


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    ok: bool
    result: object = None
    error_type: str | None = None
    error_message: str | None = None
    attempts: int = 1

    @classmethod
    def success(cls, tool_name, result, attempts=1):
        return cls(tool_name=tool_name, ok=True, result=result, attempts=attempts)

    @classmethod
    def failure(cls, tool_name, error_type, error_message, attempts=1):
        return cls(
            tool_name=tool_name,
            ok=False,
            error_type=error_type,
            error_message=error_message,
            attempts=attempts,
        )

    def to_dict(self):
        return {
            "tool_name": self.tool_name,
            "ok": self.ok,
            "result": self.result,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "attempts": self.attempts,
        }
