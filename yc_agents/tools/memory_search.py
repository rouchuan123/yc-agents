from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class MemorySearchTool(BaseTool):
    name = "memory_search"
    description = "Search global, workspace, and prior-session memory."
    schema = ToolSchema(
        fields=[
            ToolField(name="query", type="str", required=True),
            ToolField(name="top_k", type="int", required=False, default=6),
        ]
    )

    def __init__(self, memory, session_id=None, token_budget=4000):
        self.memory = memory
        self.session_id = session_id
        self.token_budget = token_budget

    def run(self, query, top_k=6):
        results = self.memory.search(
            query,
            top_k=max(1, min(20, int(top_k))),
            token_budget=self.token_budget,
            exclude_session_id=self.session_id,
        )
        return {"query": query, "result_count": len(results), "results": results}
