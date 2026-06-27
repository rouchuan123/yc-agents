from yc_agents.eval.metrics import (
    average,
    citation_precision,
    classify_tool_events,
    conflict_awareness_success,
    forbidden_tool_success,
    keyword_success,
    noise_resistance_score,
    retrieval_hit,
    tool_success,
    tool_event_counts,
    trace_event_success,
    verification_success,
)
from yc_agents.eval.report import summarize_results


def test_keyword_success_requires_all_keywords():
    assert keyword_success("包含接口问题和技术路线", ["接口问题", "技术路线"])
    assert not keyword_success("只包含接口问题", ["接口问题", "技术路线"])


def test_tool_success_checks_required_tools():
    trace_events = [
        {"event_type": "tool_called", "payload": {"tool_name": "rag_search"}},
        {"event_type": "tool_called", "payload": {"tool_name": "markdown_writer"}},
    ]

    assert tool_success(trace_events, ["rag_search"])
    assert not tool_success(trace_events, ["docx_reader"])


def test_trace_event_success_checks_required_events():
    trace_events = [
        {"event_type": "run_started", "payload": {}},
        {"event_type": "tool_called", "payload": {"tool_name": "workspace_files"}},
    ]

    assert trace_event_success(trace_events, ["tool_called"])
    assert not trace_event_success(trace_events, ["tool_failed"])


def test_forbidden_tool_success_fails_when_forbidden_tool_called():
    trace_events = [
        {"event_type": "tool_called", "payload": {"tool_name": "web_search"}},
    ]

    assert forbidden_tool_success(trace_events, ["markdown_writer"])
    assert not forbidden_tool_success(trace_events, ["web_search"])


def test_tool_event_counts_groups_gateway_events():
    trace_events = [
        {"event_type": "tool_called", "payload": {"tool_name": "workspace_files"}},
        {"event_type": "tool_denied", "payload": {"tool_name": "web_search"}},
        {"event_type": "tool_validation_failed", "payload": {"tool_name": "rag_search"}},
        {"event_type": "tool_retry", "payload": {"tool_name": "rag_search"}},
        {
            "event_type": "tool_failed",
            "payload": {"tool_name": "rag_search", "error_type": "timeout"},
        },
        {"event_type": "tool_needs_approval", "payload": {"tool_name": "markdown_writer"}},
    ]

    counts = tool_event_counts(trace_events)

    assert counts == {
        "called": 1,
        "denied": 1,
        "validation_failed": 1,
        "retry": 1,
        "failed": 1,
        "approval_required": 1,
    }


def test_classify_tool_events_returns_human_readable_risk_labels():
    trace_events = [
        {"event_type": "tool_denied", "payload": {"tool_name": "web_search"}},
        {
            "event_type": "tool_failed",
            "payload": {"tool_name": "rag_search", "error_type": "timeout"},
        },
    ]

    labels = classify_tool_events(trace_events)

    assert labels == ["policy_denial", "tool_timeout"]


def test_retrieval_hit_checks_sources():
    results = [{"source": "code-notes.md"}, {"source": "notes.md"}]

    assert retrieval_hit(results, ["code-notes.md"])
    assert not retrieval_hit(results, ["missing.md"])


def test_citation_precision_counts_known_sources():
    citations = ["code-notes.md", "notes.md", "unknown.md"]

    assert citation_precision(citations, ["code-notes.md", "notes.md"]) == 2 / 3


def test_noise_resistance_score_rewards_relevant_top_results():
    results = [
        {"source": "gold.md", "metadata": {"label": "relevant"}},
        {"source": "noise.md", "metadata": {"label": "noise"}},
        {"source": "gold-2.md", "metadata": {"label": "relevant"}},
    ]

    assert noise_resistance_score(results) == 2 / 3


def test_conflict_awareness_success_requires_conflict_language():
    output = "资料 A 和资料 B 存在冲突，我会分别说明来源。"
    assert conflict_awareness_success(output, expects_conflict=True)
    assert not conflict_awareness_success("资料完全一致。", expects_conflict=True)
    assert conflict_awareness_success("资料完全一致。", expects_conflict=False)


def test_verification_success_reads_report():
    assert verification_success({"passed": True}) is True
    assert verification_success({"passed": False}) is False
    assert verification_success(None) is False


def test_average_empty_is_zero():
    assert average([]) == 0
    assert average([2, 4]) == 3


def test_summarize_results():
    results = [
        {"keyword_success": True, "latency_seconds": 2.0},
        {"keyword_success": False, "latency_seconds": 4.0},
    ]

    summary = summarize_results(results)

    assert summary["case_count"] == 2
    assert summary["task_success_rate"] == 0.5
    assert summary["avg_latency_seconds"] == 3.0


def test_summarize_results_includes_tool_and_trace_rates():
    results = [
        {
            "keyword_success": True,
            "tool_success": True,
            "trace_event_success": True,
            "forbidden_tool_success": True,
            "latency_seconds": 1.0,
        },
        {
            "keyword_success": False,
            "tool_success": False,
            "trace_event_success": True,
            "forbidden_tool_success": True,
            "latency_seconds": 3.0,
        },
    ]

    summary = summarize_results(results)

    assert summary["case_count"] == 2
    assert summary["task_success_rate"] == 0.5
    assert summary["tool_success_rate"] == 0.5
    assert summary["trace_event_success_rate"] == 1.0
    assert summary["forbidden_tool_success_rate"] == 1.0


def test_summarize_results_includes_tool_event_totals():
    results = [
        {
            "keyword_success": True,
            "latency_seconds": 1.0,
            "tool_event_counts": {
                "called": 2,
                "denied": 0,
                "validation_failed": 1,
                "retry": 1,
                "failed": 1,
                "approval_required": 0,
            },
            "tool_failure_labels": [
                "schema_validation",
                "retry",
                "tool_execution_error",
            ],
        }
    ]

    summary = summarize_results(results)

    assert summary["tool_event_totals"]["called"] == 2
    assert summary["tool_event_totals"]["validation_failed"] == 1
    assert summary["tool_failure_labels"] == {
        "schema_validation": 1,
        "retry": 1,
        "tool_execution_error": 1,
    }
