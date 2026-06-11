class RAGCitationFormatter:
    def format(self, query, results):
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

        return [
            f"### 依据 {index}",
            "",
            f"- 来源：{source}",
            f"- 片段：{chunk_id}",
            f"- 分数：{score}",
            "",
            f"> {text}",
            "",
        ]