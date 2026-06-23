import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MCPClientConfig:
    servers: dict

    @classmethod
    def from_file(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(servers=data.get("servers", {}))


class StaticMCPClient:
    def __init__(self, responses):
        self.responses = dict(responses)

    def call_tool(self, server_name, tool_name, arguments):
        key = (server_name, tool_name)
        if key not in self.responses:
            raise KeyError(f"No static MCP response for {server_name}.{tool_name}")
        return self.responses[key]
