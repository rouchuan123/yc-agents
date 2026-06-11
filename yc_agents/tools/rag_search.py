from yc_agents.tools.base import BaseTool


class RAGSearchTool(BaseTool):
    name = "rag_search"
    description = "Search relevant document chunks."

    def __init__(self, index):
        self.index = index

    def run(self, query, top_k=3):
        return self.index.search(query, top_k=top_k)