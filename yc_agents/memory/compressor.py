from yc_agents.memory.summary import SummaryMemory


class MemoryCompressor:
    def __init__(self, summary_memory=None, max_items=6):
        self.summary_memory = summary_memory or SummaryMemory()
        self.max_items = max_items

    def compress_messages(self, messages):
        if not messages:
            return "# 阶段摘要\n\n暂无可压缩的对话记录。"

        recent_messages = messages[-self.max_items:]

        lines = [
            "# 阶段摘要",
            "",
            "## 最近对话要点",
            "",
        ]

        for message in recent_messages:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            lines.append(f"- **{role}**：{content}")

        return "\n".join(lines)

    def compress_messages_with_metadata(self, messages):
        messages = list(messages or [])
        summary = self.compress_messages(messages)
        kept_count = min(len(messages), self.max_items)

        return {
            "summary": summary,
            "input_count": len(messages),
            "kept_count": kept_count,
            "compressed_count": max(0, len(messages) - kept_count),
        }

    def save_summary(self, summary):
        return self.summary_memory.save(summary)

    def compress_and_save(self, messages):
        summary = self.compress_messages(messages)
        self.save_summary(summary)
        return summary
