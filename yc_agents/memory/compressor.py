import json

from yc_agents.core.llm_call import invoke_llm
from yc_agents.memory.summary import SummaryMemory


def estimate_tokens(value):
    if not value:
        return 0
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return max(1, len(value) // 4)


class MemoryCompressor:
    def __init__(self, summary_memory=None, max_items=6, llm=None):
        self.summary_memory = summary_memory or SummaryMemory()
        self.max_items = max_items
        self.llm = llm

    def compress_messages(self, messages):
        if not messages:
            return "# 阶段摘要\n\n暂无可压缩的对话记录。"
        recent_messages = messages[-self.max_items:]
        lines = ["# 阶段摘要", "", "## 最近对话要点", ""]
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

    def compact_if_needed(
        self,
        messages,
        previous_summary="",
        *,
        active_max_tokens=64_000,
        context_limit=8_000,
        trigger_percent=80,
        target_percent=50,
        max_output_tokens=0,
        additional_tokens=0,
    ):
        messages = list(messages or [])
        active_tokens = estimate_tokens(messages)
        summary_tokens = estimate_tokens(previous_summary)
        total_estimate = active_tokens + summary_tokens + max(0, int(additional_tokens))
        usable_window = max(1, int(context_limit or 1) - max(0, int(max_output_tokens or 0)))
        window_trigger = usable_window * max(1, int(trigger_percent)) // 100
        active_triggered = active_tokens > max(1, int(active_max_tokens))
        window_triggered = total_estimate > window_trigger

        if not active_triggered and not window_triggered:
            return self._result(messages, previous_summary, False, 0, active_tokens)

        active_target = max(
            1,
            int(active_max_tokens) * max(1, int(target_percent)) // 100,
        )
        window_target = max(1, usable_window * max(1, int(target_percent)) // 100)
        target_messages = min(
            active_target,
            max(1, window_target - summary_tokens - max(0, int(additional_tokens))),
        )
        split_index = self._select_prefix(messages, target_messages)
        if split_index <= 0:
            return self._result(messages, previous_summary, False, 0, active_tokens)

        prefix = messages[:split_index]
        retained = messages[split_index:]
        old_tokens = estimate_tokens(prefix) + summary_tokens
        summary = self._summarize(previous_summary, prefix)
        if not summary or estimate_tokens(summary) > int(old_tokens * 0.8):
            summary = self._deterministic_summary(previous_summary, prefix, old_tokens)
        if not summary or estimate_tokens(summary) > int(old_tokens * 0.8):
            return self._result(messages, previous_summary, False, 0, active_tokens)

        self.save_summary(summary)
        return self._result(
            retained,
            summary,
            True,
            len(prefix),
            estimate_tokens(retained) + estimate_tokens(summary),
        )

    def _select_prefix(self, messages, target_tokens):
        if len(messages) < 4:
            return 0
        keep_from = len(messages)
        retained_tokens = 0
        for index in range(len(messages) - 1, -1, -1):
            retained_tokens += estimate_tokens(messages[index])
            if retained_tokens > target_tokens:
                break
            keep_from = index
        keep_from = min(keep_from, max(0, len(messages) - 2))
        while keep_from > 0 and messages[keep_from].get("role") != "user":
            keep_from -= 1
        return keep_from

    def _summarize(self, previous_summary, messages):
        if self.llm is None:
            return ""
        prompt = [
            {
                "role": "system",
                "content": (
                    "Compress conversation history into durable Markdown. Use these "
                    "headings: Goals, Facts, Decisions, Changes, Open Items, User "
                    "Preferences. Preserve paths, errors, decisions, and unfinished work."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"previous_summary": previous_summary, "messages": messages},
                    ensure_ascii=False,
                ),
            },
        ]
        try:
            return str(invoke_llm(self.llm.think, prompt, usage_kind="auxiliary") or "").strip()
        except Exception:
            return ""

    def _deterministic_summary(self, previous_summary, messages, old_tokens):
        max_chars = max(100, int(old_tokens * 0.78) * 4)
        lines = ["# Conversation Summary"]
        if previous_summary.strip():
            lines.extend(["", "## Previous", previous_summary.strip()])
        lines.extend(["", "## Compacted History"])
        remaining = max(0, max_chars - len("\n".join(lines)) - 1)
        for message in messages:
            role = str(message.get("role") or "unknown")
            content = str(message.get("content") or "").strip().replace("\n", " ")
            if not content:
                continue
            entry = f"- {role}: {content}"
            if len(entry) > remaining:
                entry = entry[: max(0, remaining - 3)] + "..."
            if entry:
                lines.append(entry)
                remaining -= len(entry)
            if remaining <= 20:
                break
        return "\n".join(lines).strip()

    @staticmethod
    def _result(messages, summary, compacted, compacted_count, estimated_tokens):
        return {
            "messages": list(messages),
            "summary": str(summary or ""),
            "compacted": bool(compacted),
            "compacted_count": int(compacted_count),
            "estimated_tokens": max(0, int(estimated_tokens)),
        }
