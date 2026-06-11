class VectorStore:
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
                    "embedding": None,
                }
            )

    def search(self, query, top_k=3):
        raise NotImplementedError("Vector search is not implemented yet.")

    def list_items(self):
        return list(self.items)