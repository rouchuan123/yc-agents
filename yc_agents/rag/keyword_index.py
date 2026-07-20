import re

from rank_bm25 import BM25Okapi

from yc_agents.rag.document import DocumentChunk


ASCII_WORD = re.compile(r"[a-zA-Z0-9_./:-]+")
CJK_RUN = re.compile(r"[\u3400-\u9fff]+")


def keyword_tokens(text):
    text = str(text or "").lower()
    tokens = ASCII_WORD.findall(text)
    for run in CJK_RUN.findall(text):
        tokens.extend(
            run
            if len(run) == 1
            else [run[index : index + 2] for index in range(len(run) - 1)]
        )
    return tokens


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

    def clear(self):
        self.items.clear()

    def search(self, query, top_k=3):
        if not query or not query.strip():
            return []

        query_terms = keyword_tokens(query)
        if not query_terms or not self.items:
            return []

        corpus = [keyword_tokens(item["text"]) or [""] for item in self.items]
        raw_scores = BM25Okapi(corpus).get_scores(query_terms)
        normalized_scores = self._normalize(raw_scores)
        query_set = set(query_terms)
        results = []

        for item, terms, bm25_score in zip(self.items, corpus, normalized_scores):
            lexical_score = len(query_set & set(terms)) / len(query_set)
            score = max(float(bm25_score), lexical_score)

            if score <= 0:
                continue

            results.append(
                {
                    "source": item["source"],
                    "chunk_id": item["chunk_id"],
                    "score": score,
                    "text": item["text"],
                    "metadata": dict(item.get("metadata", {})),
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]

    @staticmethod
    def _normalize(values):
        values = [float(value) for value in values]
        if not values:
            return []
        low, high = min(values), max(values)
        if high <= low:
            return [1.0 if value > 0 else 0.0 for value in values]
        return [(value - low) / (high - low) for value in values]
