class QueryTermReranker:
    def rerank(self, query, results):
        terms = [term for term in query.lower().split() if term]

        def rerank_score(result):
            text = result.get("text", "").lower()
            term_hits = sum(1 for term in terms if term in text)
            return (term_hits, result.get("score", 0))

        return sorted(results, key=rerank_score, reverse=True)
