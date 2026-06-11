class KeywordIndex:
    def __init__(self):
        self.items = []

    def add_chunks(self, source, chunks):
        for chunk_id, chunk in enumerate(chunks):
            text = chunk.strip()

            if not text:
                continue

            self.items.append(
                {
                    "source": source,
                    "chunk_id": chunk_id,
                    "text": text,
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
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]