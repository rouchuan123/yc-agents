from yc_agents.memory.compressor import MemoryCompressor, estimate_tokens
from yc_agents.memory.summary import SummaryMemory


def messages(count=8, size=300):
    result = []
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        result.append({"role": role, "content": f"{index}:" + ("x" * size)})
    return result


def chinese_messages(count=8, size=300):
    result = []
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        result.append({"role": role, "content": f"{index}:" + ("测" * size)})
    return result


def test_estimate_tokens_counts_cjk_characters_individually():
    assert estimate_tokens("中" * 120) == 120
    assert estimate_tokens("あ" * 7) == 7
    assert estimate_tokens("ア" * 6) == 6
    assert estimate_tokens("가" * 5) == 5


def test_estimate_tokens_keeps_ascii_quarter_rate():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("a" * 120) == 30


def test_estimate_tokens_mixed_text_sums_per_category():
    assert estimate_tokens("中文注释" + "code" * 3) == 7
    assert estimate_tokens("д" * 9) == 3


def test_chinese_history_triggers_compaction(tmp_path):
    summary_memory = SummaryMemory(tmp_path / "summary.md")
    compressor = MemoryCompressor(summary_memory=summary_memory)
    original = chinese_messages()

    # 旧的 len//4 估算把 2400 个汉字算成 ~670 tokens，永远到不了 1200 的
    # 压缩线；按 CJK 每字 ~1 token 估算后必须触发压缩。
    result = compressor.compact_if_needed(
        original,
        active_max_tokens=1200,
        context_limit=1_000_000,
    )

    assert result["compacted"] is True
    assert result["estimated_tokens"] < estimate_tokens(original)
    assert summary_memory.load().startswith("# Conversation Summary")


def test_token_compaction_keeps_complete_recent_turn_and_saves_summary(tmp_path):
    summary_memory = SummaryMemory(tmp_path / "summary.md")
    compressor = MemoryCompressor(summary_memory=summary_memory)
    original = messages()

    result = compressor.compact_if_needed(
        original,
        active_max_tokens=200,
        context_limit=10_000,
    )

    assert result["compacted"] is True
    assert result["messages"][0]["role"] == "user"
    assert len(result["messages"]) >= 2
    assert result["compacted_count"] + len(result["messages"]) == len(original)
    assert summary_memory.load().startswith("# Conversation Summary")
    assert result["estimated_tokens"] < estimate_tokens(original)


def test_compaction_reserves_output_and_uses_window_trigger(tmp_path):
    compressor = MemoryCompressor(summary_memory=SummaryMemory(tmp_path / "summary.md"))
    result = compressor.compact_if_needed(
        messages(size=700),
        active_max_tokens=100_000,
        context_limit=2_000,
        max_output_tokens=500,
        trigger_percent=80,
        target_percent=50,
    )
    assert result["compacted"] is True


def test_compaction_uses_configured_percent_for_active_target(tmp_path):
    class CapturingCompressor(MemoryCompressor):
        def _select_prefix(self, items, target_tokens):
            self.target_tokens = target_tokens
            return 0

    compressor = CapturingCompressor(
        summary_memory=SummaryMemory(tmp_path / "summary.md")
    )

    compressor.compact_if_needed(
        messages(),
        active_max_tokens=200,
        context_limit=10_000,
        target_percent=30,
    )

    assert compressor.target_tokens == 60


def test_small_history_is_not_compacted(tmp_path):
    compressor = MemoryCompressor(summary_memory=SummaryMemory(tmp_path / "summary.md"))
    original = messages(count=2, size=10)
    result = compressor.compact_if_needed(original, active_max_tokens=1)
    assert result["compacted"] is False
    assert result["messages"] == original
