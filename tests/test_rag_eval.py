import json

from yc_agents.eval.case import EvalCase, load_cases
from yc_agents.eval.runner import run_cases
from yc_agents.rag.citation_formatter import RAGCitationFormatter


def test_citation_formatter_outputs_readable_chinese_and_sources():
    formatter = RAGCitationFormatter()

    output = formatter.format(
        "接口问题",
        [
            {
                "source": "demo.md",
                "chunk_id": 1,
                "score": 0.8,
                "text": "接口问题来自多智能体协作。",
                "metadata": {"section": "背景"},
            }
        ],
    )

    assert output["type"] == "rag_search_result"
    assert "RAG 检索结果" in output["text"]
    assert output["sources"] == ["demo.md"]
    assert output["results"][0]["metadata"]["section"] == "背景"


def test_rag_formatter_returns_structured_sources():
    formatter = RAGCitationFormatter()
    results = [
        {
            "source": "agent-notes.md",
            "chunk_id": "chunk-1",
            "content": "Agent eval should check tool traces.",
            "score": 0.8,
        }
    ]

    formatted = formatter.format("agent eval", results)

    assert formatted["type"] == "rag_search_result"
    assert formatted["query"] == "agent eval"
    assert formatted["sources"] == ["agent-notes.md"]
    assert formatted["results"][0]["source"] == "agent-notes.md"


def test_load_cases_accepts_rag_noise_fields(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "rag-conflict-001",
                "category": "rag",
                "input": "比较两份资料",
                "expected_keywords": ["冲突"],
                "reference_sources": ["gold.md"],
                "expects_conflict": True,
                "min_noise_resistance": 0.5,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    case = load_cases(path)[0]

    assert case.expects_conflict is True
    assert case.min_noise_resistance == 0.5


class FakeRAGRuntime:
    def __init__(self):
        self.last_trace_events = []

    def run(self, user_input):
        self.last_trace_events = [
            {
                "event_type": "tool_called",
                "payload": {
                    "tool_name": "rag_search",
                    "result": {
                        "type": "rag_search_result",
                        "sources": ["gold.md", "noise.md"],
                        "results": [
                            {"source": "gold.md", "metadata": {"label": "relevant"}},
                            {"source": "noise.md", "metadata": {"label": "noise"}},
                        ],
                    },
                },
            }
        ]
        return "两份资料存在冲突，需要分别说明来源。"


def test_run_cases_adds_rag_noise_and_conflict_metrics():
    case = EvalCase(
        id="rag-1",
        category="rag",
        input="比较资料",
        expected_keywords=["冲突"],
        reference_sources=["gold.md"],
        expects_conflict=True,
        min_noise_resistance=0.5,
    )

    result = run_cases(FakeRAGRuntime(), [case])[0]

    assert result["retrieval_hit"] is True
    assert result["noise_resistance_score"] == 0.5
    assert result["noise_resistance_success"] is True
    assert result["conflict_awareness_success"] is True
