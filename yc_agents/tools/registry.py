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

    def to_openai_schema(self):
        """把注册表导出成 OpenAI tools 数组，供原生 function calling 传给模型。
        没有声明 schema 的工具导出开放对象参数，由工具自身在运行时校验。"""
        tools = []
        for tool in self.tools.values():
            schema = getattr(tool, "schema", None)
            parameters = (
                schema.to_openai_schema()
                if schema is not None
                else {"type": "object", "properties": {}}
            )
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": parameters,
                    },
                }
            )
        return tools

    def list_tools(self):
        tools = []
        for tool in self.tools.values():
            item = {
                "name": tool.name,
                "description": tool.description,
            }
            schema = getattr(tool, "schema", None)
            if schema is not None:
                item["parameters"] = [
                    {
                        "name": field.name,
                        "type": field.type,
                        "required": field.required,
                        "default": field.default,
                    }
                    for field in schema.fields
                ]
            tools.append(item)
        return tools
