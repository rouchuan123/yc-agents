from yc_agents.rag.document import DocumentChunk


class KeywordIndex:
    def __init__(self):
        self.items = []

    def add_chunks(self, source, chunks):
        for fallback_chunk_id, chunk in enumerate(chunks):
            if isinstance(chunk, DocumentChunk):
                text = chunk.text.strip()
                chunk_source = chunk.source
                chunk_id = chunk.chunk_id
                metadata = dict(chunk.metadata)
            else:
                text = chunk.strip()
                chunk_source = source
                chunk_id = fallback_chunk_id
                metadata = {}

            if not text:
                continue

            self.items.append(
                {
                    "source": chunk_source,
                    "chunk_id": chunk_id,
                    "text": text,
                    "metadata": metadata,
                }
            )

    def search(self, query, top_k=3):
        if not query or not query.strip():
            return []

        normalized_query = query.lower().strip()
        results = []

        for item in self.items:
            text = item["text"]
            score = text.lower().count(normalized_query)

            if score <= 0:
                continue

            results.append(
                {
                    "source": item["source"],
                    "chunk_id": item["chunk_id"],
                    "score": score,
                    "text": text,
                    "metadata": dict(item.get("metadata", {})),
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]
