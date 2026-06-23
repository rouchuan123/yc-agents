from yc_agents.rag.embeddings import DeterministicEmbeddingProvider
from yc_agents.rag.document import DocumentChunk
from yc_agents.rag.hybrid_retriever import HybridRetriever
from yc_agents.rag.keyword_index import KeywordIndex
from yc_agents.rag.vector_store import VectorStore


def test_vector_store_search_returns_ranked_results():
    provider = DeterministicEmbeddingProvider(dimensions=8)
    store = VectorStore(embedding_provider=provider)
    store.add_chunks("demo.md", ["研究背景", "完全不同的内容"])

    results = store.search("研究背景", top_k=1)

    assert len(results) == 1
    assert results[0]["source"] == "demo.md"
    assert "score" in results[0]
    assert "metadata" in results[0]


def test_keyword_index_accepts_metadata_chunks():
    index = KeywordIndex()
    index.add_chunks(
        "ignored.md",
        [
            DocumentChunk(
                source="demo.md",
                chunk_id=7,
                text="研究背景",
                metadata={"section": "背景"},
            )
        ],
    )

    results = index.search("研究背景", top_k=1)

    assert results[0]["source"] == "demo.md"
    assert results[0]["chunk_id"] == 7
    assert results[0]["metadata"]["section"] == "背景"


def test_hybrid_retriever_merges_keyword_and_vector_results():
    provider = DeterministicEmbeddingProvider(dimensions=8)
    keyword = KeywordIndex()
    vector = VectorStore(embedding_provider=provider)
    keyword.add_chunks("demo.md", ["研究背景"])
    vector.add_chunks("demo.md", ["研究背景"])
    retriever = HybridRetriever(keyword_index=keyword, vector_store=vector)

    results = retriever.search("研究背景", top_k=3)

    assert results
    assert results[0]["source"] == "demo.md"
    assert "keyword_score" in results[0]
    assert "vector_score" in results[0]
