from yc_agents.eval.metrics import (
    average,
    citation_precision,
    keyword_success,
    retrieval_hit,
    tool_success,
)
from yc_agents.eval.report import summarize_results


def test_keyword_success_requires_all_keywords():
    assert keyword_success("包含研究问题和技术路线", ["研究问题", "技术路线"])
    assert not keyword_success("只包含研究问题", ["研究问题", "技术路线"])


def test_tool_success_checks_required_tools():
    trace_events = [
        {"event_type": "tool_called", "payload": {"tool_name": "rag_search"}},
        {"event_type": "tool_called", "payload": {"tool_name": "markdown_writer"}},
    ]

    assert tool_success(trace_events, ["rag_search"])
    assert not tool_success(trace_events, ["docx_reader"])


def test_retrieval_hit_checks_sources():
    results = [{"source": "paper.md"}, {"source": "notes.md"}]

    assert retrieval_hit(results, ["paper.md"])
    assert not retrieval_hit(results, ["missing.md"])


def test_citation_precision_counts_known_sources():
    citations = ["paper.md", "notes.md", "unknown.md"]

    assert citation_precision(citations, ["paper.md", "notes.md"]) == 2 / 3


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
