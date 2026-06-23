from yc_agents.tools.rag_search import RAGSearchTool


class FakeRetriever:
    def __init__(self):
        self.calls = []

    def search(self, query, top_k=3):
        self.calls.append({"query": query, "top_k": top_k})
        return [
            {
                "source": "demo.md",
                "chunk_id": 0,
                "score": 1,
                "text": "研究背景",
                "metadata": {"section": "背景"},
            }
        ]


def test_rag_search_tool_accepts_injected_retriever_and_formats_results():
    retriever = FakeRetriever()
    tool = RAGSearchTool(retriever)

    result = tool.run("研究背景", top_k=2)

    assert retriever.calls == [{"query": "研究背景", "top_k": 2}]
    assert "RAG 检索结果" in result
    assert "demo.md" in result
    assert "背景" in result
