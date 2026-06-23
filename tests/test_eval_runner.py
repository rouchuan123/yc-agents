import json

from yc_agents.eval.case import EvalCase, load_cases
from yc_agents.eval.runner import run_cases


def test_load_cases_from_jsonl(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "case-1",
                "category": "rag_qa",
                "input": "总结资料中的研究问题",
                "expected_keywords": ["研究问题"],
                "required_tools": ["rag_search"],
                "reference_sources": ["paper.md"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_cases(path)

    assert cases == [
        EvalCase(
            id="case-1",
            category="rag_qa",
            input="总结资料中的研究问题",
            expected_keywords=["研究问题"],
            required_tools=["rag_search"],
            reference_sources=["paper.md"],
        )
    ]


class FakeRuntime:
    def run(self, user_input):
        return f"研究问题 技术路线 output for {user_input}"


def test_run_cases_with_fake_runtime():
    case = EvalCase(
        id="case-1",
        category="opening_report",
        input="写开题大纲",
        expected_keywords=["研究问题", "技术路线"],
    )

    results = run_cases(FakeRuntime(), [case])

    assert results[0]["case_id"] == "case-1"
    assert results[0]["keyword_success"] is True
    assert results[0]["latency_seconds"] >= 0
