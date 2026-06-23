from yc_agents.tools.base import BaseTool
from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.rag.citation_formatter import RAGCitationFormatter


class RAGSearchTool(BaseTool):
    name = "rag_search"
    description = "Search relevant document chunks."
    schema = ToolSchema(
        fields=[
            ToolField(name="query", type="str", required=True),
            ToolField(name="top_k", type="int", required=False, default=3),
        ]
    )

    def __init__(self, retriever, formatter=None):
        self.retriever = retriever
        self.formatter = formatter or RAGCitationFormatter()

    def run(self, query, top_k=3):
        results = self.retriever.search(query, top_k=top_k)
        return self.formatter.format(query, results)
