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
                "text": "接口说明",
                "metadata": {"section": "背景"},
            }
        ]


def test_rag_search_tool_accepts_injected_retriever_and_formats_results():
    retriever = FakeRetriever()
    tool = RAGSearchTool(retriever)

    result = tool.run("接口说明", top_k=2)

    assert retriever.calls == [{"query": "接口说明", "top_k": 2}]
    assert result["type"] == "rag_search_result"
    assert "RAG 检索结果" in result["text"]
    assert result["sources"] == ["demo.md"]
    assert result["results"][0]["metadata"]["section"] == "背景"
