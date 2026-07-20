from yc_agents.tools.base import BaseTool
from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.rag.citation_formatter import RAGCitationFormatter


class RAGSearchTool(BaseTool):
    name = "rag_search"
    description = (
        "Search the active workspace knowledge base and return relevant document "
        "chunks with source citations."
    )

    def __init__(self, retriever, formatter=None, default_top_k=4):
        self.retriever = retriever
        self.formatter = formatter or RAGCitationFormatter()
        self.default_top_k = max(1, int(default_top_k))
        self.schema = ToolSchema(
            fields=[
                ToolField(name="query", type="str", required=True),
                ToolField(
                    name="top_k",
                    type="int",
                    required=False,
                    default=self.default_top_k,
                ),
            ]
        )

    def run(self, query, top_k=None):
        top_k = self.default_top_k if top_k is None else max(1, int(top_k))
        results = self.retriever.search(query, top_k=top_k)
        return self.formatter.format(query, results)
