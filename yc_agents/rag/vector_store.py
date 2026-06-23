import numpy as np

from yc_agents.rag.document import DocumentChunk
from yc_agents.rag.embeddings import DeterministicEmbeddingProvider


class VectorStore:
    def __init__(self, embedding_provider=None):
        self.items = []
        self.embedding_provider = embedding_provider or DeterministicEmbeddingProvider()

    def add_chunks(self, source, chunks):
        chunk_records = []

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

            chunk_records.append((chunk_source, chunk_id, text, metadata))

        embeddings = self.embedding_provider.embed(
            [record[2] for record in chunk_records]
        )

        for (chunk_source, chunk_id, text, metadata), embedding in zip(
            chunk_records,
            embeddings,
        ):
            self.items.append(
                {
                    "source": chunk_source,
                    "chunk_id": chunk_id,
                    "text": text,
                    "metadata": metadata,
                    "embedding": embedding,
                }
            )

    def search(self, query, top_k=3):
        if not query or not query.strip():
            return []

        query_vector = np.array(self.embedding_provider.embed([query])[0], dtype=float)
        query_norm = np.linalg.norm(query_vector)
        if query_norm == 0:
            return []

        results = []
        for item in self.items:
            item_vector = np.array(item["embedding"], dtype=float)
            item_norm = np.linalg.norm(item_vector)
            score = 0 if item_norm == 0 else float(
                np.dot(query_vector, item_vector) / (query_norm * item_norm)
            )
            results.append(
                {
                    "source": item["source"],
                    "chunk_id": item["chunk_id"],
                    "score": score,
                    "text": item["text"],
                    "metadata": dict(item.get("metadata", {})),
                }
            )

        return sorted(results, key=lambda item: item["score"], reverse=True)[:top_k]

    def list_items(self):
        return list(self.items)
