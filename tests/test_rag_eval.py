from yc_agents.rag.citation_formatter import RAGCitationFormatter


def test_citation_formatter_outputs_readable_chinese_and_sources():
    formatter = RAGCitationFormatter()

    output = formatter.format(
        "研究问题",
        [
            {
                "source": "demo.md",
                "chunk_id": 1,
                "score": 0.8,
                "text": "研究问题来自多智能体协作。",
                "metadata": {"section": "背景"},
            }
        ],
    )

    assert "RAG 检索结果" in output
    assert "demo.md" in output
    assert "背景" in output
