import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "eval" / "cases"


def _load_jsonl(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_eval_case_files_are_code_agent_focused():
    expected = {
        "code_review_cases.jsonl",
        "context_cases.jsonl",
        "eval_writer_cases.jsonl",
        "runtime_cases.jsonl",
        "toolgateway_cases.jsonl",
    }

    actual = {path.name for path in CASE_DIR.glob("*.jsonl")}

    assert expected.issubset(actual)
    assert "research_agent_cases.jsonl" not in actual
    assert "rag_cases.jsonl" not in actual
    assert "rag_noise_cases.jsonl" not in actual


def test_eval_cases_do_not_use_old_domain_terms():
    forbidden_terms = [
        "论文" + "助手",
        "文献" + "综述",
        "开题" + "报告",
        "研究" + "背景",
        "研究" + "问题",
        "多智能体" + "论文",
        "demo-research-notes.md",
    ]

    for path in CASE_DIR.glob("*.jsonl"):
        text = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in text, f"{term} remains in {path.name}"


def test_code_review_cases_cover_review_evidence_loop():
    cases = _load_jsonl(CASE_DIR / "code_review_cases.jsonl")
    categories = {case["category"] for case in cases}

    assert {"project_audit", "change_review", "test_gap"}.issubset(categories)
    assert any("code_search" in case.get("required_tools", []) for case in cases)
    assert any("git_inspector" in case.get("required_tools", []) for case in cases)
    assert any("verification_runner" in case.get("required_tools", []) for case in cases)
