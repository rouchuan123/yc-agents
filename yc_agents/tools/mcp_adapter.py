from yc_agents.tools.base import BaseTool


class MCPToolAdapter(BaseTool):
    def __init__(
        self,
        name,
        description,
        server_name,
        tool_name,
        client,
        schema=None,
    ):
        self.name = name
        self.description = description
        self.server_name = server_name
        self.tool_name = tool_name
        self.client = client
        self.schema = schema

    def run(self, **arguments):
        result = self.client.call_tool(
            self.server_name,
            self.tool_name,
            arguments,
        )

        return {
            "type": "mcp_tool_result",
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "result": result,
        }
