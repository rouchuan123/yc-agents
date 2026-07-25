import json
from dataclasses import dataclass, field


class ToolLoopError(RuntimeError):
    pass


@dataclass
class ToolExecutionPolicy:
    max_calls: int = 100
    max_repeated_calls: int = 5
    timeout_seconds: float = 30
    max_retries: int = 1
    call_count: int = 0
    repeated_calls: dict[str, int] = field(default_factory=dict)
    last_call_key: str = ""
    consecutive_repeated_calls: int = 0

    def record_call(self, name, arguments):
        self.call_count += 1
        if self.call_count > self.max_calls:
            raise ToolLoopError(f"Maximum tool calls exceeded: {self.max_calls}")

        key = json.dumps(
            {"name": name, "arguments": arguments},
            sort_keys=True,
            ensure_ascii=False,
        )
        if key == self.last_call_key:
            self.consecutive_repeated_calls += 1
        else:
            self.last_call_key = key
            self.consecutive_repeated_calls = 1
            self.repeated_calls.clear()
        self.repeated_calls[key] = self.consecutive_repeated_calls

        if self.consecutive_repeated_calls > self.max_repeated_calls:
            raise ToolLoopError(f"Repeated tool call blocked: {name}")
