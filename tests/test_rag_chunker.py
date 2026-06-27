from yc_agents.rag.chunker import DocumentChunker
from yc_agents.rag.document import DocumentChunk


def test_chunk_text_with_metadata():
    chunker = DocumentChunker(chunk_size=10, overlap=2)

    chunks = chunker.chunk_text(
        "接口说明和技术路线需要被切片",
        source="demo.md",
        metadata={"section": "背景"},
    )

    assert isinstance(chunks[0], DocumentChunk)
    assert chunks[0].source == "demo.md"
    assert chunks[0].chunk_id == 0
    assert chunks[0].metadata["section"] == "背景"
    assert chunks[0].text


def test_chunk_text_without_metadata_keeps_string_chunks():
    chunker = DocumentChunker(chunk_size=10, overlap=2)

    chunks = chunker.chunk_text("接口说明和技术路线")

    assert isinstance(chunks[0], str)
