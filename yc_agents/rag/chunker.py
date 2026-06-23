from yc_agents.rag.document import DocumentChunk


class DocumentChunker:
    def __init__(self, chunk_size=500, overlap=50):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        if overlap < 0:
            raise ValueError("overlap must be non-negative")

        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text, source=None, metadata=None):
        if not text or not text.strip():
            return []

        clean_text = text.strip()
        chunks = []
        start = 0

        while start < len(clean_text):
            end = start + self.chunk_size
            chunk = clean_text[start:end].strip()

            if chunk:
                chunks.append(chunk)

            start = end - self.overlap

        if source is not None or metadata is not None:
            chunk_source = source or "unknown"
            chunk_metadata = dict(metadata or {})
            return [
                DocumentChunk(
                    source=chunk_source,
                    chunk_id=chunk_id,
                    text=chunk,
                    metadata=dict(chunk_metadata),
                )
                for chunk_id, chunk in enumerate(chunks)
            ]

        return chunks
