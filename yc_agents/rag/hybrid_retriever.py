class HybridRetriever:
    def __init__(
        self,
        keyword_index,
        vector_store,
        keyword_weight=0.5,
        vector_weight=0.5,
    ):
        self.keyword_index = keyword_index
        self.vector_store = vector_store
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight

    def search(self, query, top_k=5):
        keyword_results = self.keyword_index.search(query, top_k=top_k)
        vector_results = self.vector_store.search(query, top_k=top_k)
        merged = {}

        for result in keyword_results:
            key = (result["source"], result["chunk_id"])
            merged.setdefault(key, dict(result))
            merged[key]["keyword_score"] = result.get("score", 0)

        for result in vector_results:
            key = (result["source"], result["chunk_id"])
            merged.setdefault(key, dict(result))
            merged[key]["vector_score"] = result.get("score", 0)

        for result in merged.values():
            result.setdefault("metadata", {})
            result.setdefault("keyword_score", 0)
            result.setdefault("vector_score", 0)
            result["score"] = (
                self.keyword_weight * result["keyword_score"]
                + self.vector_weight * result["vector_score"]
            )

        return sorted(
            merged.values(),
            key=lambda item: item["score"],
            reverse=True,
        )[:top_k]
