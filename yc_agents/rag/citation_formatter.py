class RAGCitationFormatter:
    def format(self, query, results):
        normalized = []

        for index, result in enumerate(results or [], start=1):
            content = result.get("content", result.get("text", ""))
            normalized.append(
                {
                    "rank": index,
                    "source": result.get("source"),
                    "chunk_id": result.get("chunk_id"),
                    "content": content,
                    "text": content,
                    "score": result.get("score", 0),
                    "metadata": result.get("metadata", {}),
                }
            )

        sources = []
        for item in normalized:
            source = item.get("source")
            if source and source not in sources:
                sources.append(source)

        return {
            "type": "rag_search_result",
            "query": query,
            "results": normalized,
            "sources": sources,
            "text": self._format_text(query, normalized),
        }

    def _format_text(self, query, results):
        lines = [
            "# RAG 检索结果",
            "",
            f"查询：{query}",
            "",
        ]

        if not results:
            lines.append("未找到相关资料片段。")
            return "\n".join(lines)

        lines.extend(
            [
                "## 依据片段",
                "",
            ]
        )

        for index, result in enumerate(results, start=1):
            lines.extend(self._format_result(index, result))

        return "\n".join(lines)

    def _format_result(self, index, result):
        source = result.get("source", "unknown")
        chunk_id = result.get("chunk_id", "unknown")
        score = result.get("score", 0)
        text = result.get("text", "")
        metadata = result.get("metadata", {}) or {}
        section = metadata.get("section")

        lines = [
            f"### 依据 {index}",
            "",
            f"- 来源：{source}",
            f"- 片段：{chunk_id}",
            f"- 分数：{score}",
        ]

        if section:
            lines.append(f"- 章节：{section}")

        lines.extend(
            [
                "",
                f"> {text}",
                "",
            ]
        )
        return lines
