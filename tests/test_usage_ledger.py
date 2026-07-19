import json
from pathlib import Path

from yc_agents.core.usage import TokenUsage, UsageLedger


def test_provider_usage_normalizes_openai_details():
    details = type("Details", (), {"cached_tokens": 400})()
    output_details = type("OutputDetails", (), {"reasoning_tokens": 20})()
    wire = type(
        "Usage",
        (),
        {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "total_tokens": 1200,
            "prompt_tokens_details": details,
            "completion_tokens_details": output_details,
        },
    )()

    usage = TokenUsage.from_provider(wire)

    assert usage == TokenUsage(1000, 200, 1200, 400, 20)


def test_auxiliary_usage_accumulates_without_replacing_context(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.json")
    ledger.record(TokenUsage(100, 20, 120), "main", "primary", "provider")
    ledger.record(TokenUsage(30, 5, 35), "summary", "auxiliary", "provider")

    assert ledger.current_context.total_tokens == 120
    assert ledger.session_totals.total_tokens == 155
    assert ledger.primary_calls == 1
    assert ledger.auxiliary_calls == 1


def test_usage_ledger_persists_and_recovers_from_corruption(tmp_path):
    path = tmp_path / "usage.json"
    ledger = UsageLedger(path)
    ledger.record(TokenUsage(90, 10, 100), "m", source="estimated")

    restored = UsageLedger(path)
    assert restored.current_context.source == "estimated"
    assert restored.current_context.total_tokens == 100
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1

    path.write_text("{broken", encoding="utf-8")
    broken = UsageLedger(path)
    assert broken.current_context is None
    assert broken.session_totals.total_tokens == 0
