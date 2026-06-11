from yc_agents.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, tool):
        if not isinstance(tool, BaseTool):
            raise TypeError("tool must be an instance of BaseTool")

        if not tool.name:
            raise ValueError("tool.name is required")

        self.tools[tool.name] = tool
        return tool

    def get_tool(self, name):
        if name not in self.tools:
            raise KeyError(f"Tool not registered: {name}")

        return self.tools[name]

    def run_tool(self, name, *args, **kwargs):
        tool = self.get_tool(name)
        return tool.run(*args, **kwargs)

    def list_tools(self):
        return [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in self.tools.values()
        ]