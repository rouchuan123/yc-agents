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
        # 入库即分词的增量语料：search 只做打分，不再重扫全量文本。
        self._token_corpus = []
        # 语料指纹：任何增删都会推进版本号，BM25 只在指纹变化时重建。
        self._corpus_version = 0
        self._bm25 = None
        self._bm25_version = -1

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
            self._token_corpus.append(keyword_tokens(text) or [""])
            self._corpus_version += 1

    def clear(self):
        self.items.clear()
        self._token_corpus.clear()
        self._corpus_version += 1
        self._bm25 = None
        self._bm25_version = -1

    def search(self, query, top_k=3):
        if not query or not query.strip():
            return []

        query_terms = keyword_tokens(query)
        if not query_terms or not self.items:
            return []

        corpus = self._token_corpus
        raw_scores = self._ensure_bm25().get_scores(query_terms)
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

    def _ensure_bm25(self):
        if self._bm25 is None or self._bm25_version != self._corpus_version:
            self._bm25 = BM25Okapi(self._token_corpus)
            self._bm25_version = self._corpus_version
        return self._bm25

    @staticmethod
    def _normalize(values):
        values = [float(value) for value in values]
        if not values:
            return []
        low, high = min(values), max(values)
        if high <= low:
            return [1.0 if value > 0 else 0.0 for value in values]
        return [(value - low) / (high - low) for value in values]
