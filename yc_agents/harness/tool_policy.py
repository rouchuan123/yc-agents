import json
from dataclasses import dataclass, field


class ToolLoopError(RuntimeError):
    pass


@dataclass
class ToolExecutionPolicy:
    max_calls: int = 8
    max_repeated_calls: int = 2
    timeout_seconds: float = 30
    max_retries: int = 1
    call_count: int = 0
    repeated_calls: dict[str, int] = field(default_factory=dict)

    def record_call(self, name, arguments):
        self.call_count += 1
        if self.call_count > self.max_calls:
            raise ToolLoopError(f"Maximum tool calls exceeded: {self.max_calls}")

        key = json.dumps(
            {"name": name, "arguments": arguments},
            sort_keys=True,
            ensure_ascii=False,
        )
        self.repeated_calls[key] = self.repeated_calls.get(key, 0) + 1

        if self.repeated_calls[key] > self.max_repeated_calls:
            raise ToolLoopError(f"Repeated tool call blocked: {name}")
