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


def test_eval_case_files_are_generic_workspace_focused():
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


def test_eval_cases_do_not_use_old_or_wrong_domain_terms():
    forbidden_terms = [
        "论文" + "助手",
        "文献" + "综述",
        "开题" + "报告",
        "研究" + "背景",
        "研究" + "问题",
        "多智能体" + "论文",
        "demo-research-notes.md",
        "SkillRuntimeAgent",
        "ToolGateway 的 retry",
        "YCore code agent 的架构边界",
        "trace/state/final_output",
        "code-agent-notes.md",
        "GitHub HQ",
        "RepoService",
        "GitRunner",
        "status_parser",
        "Tkinter",
        "Ycore-demo",
        "当前仓库未提交改动",
        "当前工作区未提交改动",
    ]

    for path in CASE_DIR.glob("*.jsonl"):
        text = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in text, f"{term} remains in {path.name}"


def test_eval_cases_require_workspace_fact_discovery():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in CASE_DIR.glob("*.jsonl")
    )

    assert "先探测工作区事实" in text
    assert "不要假设" in text
    assert ".git" in text
    assert "README" in text
    assert "如果不存在" in text


def test_code_review_cases_cover_generic_review_evidence_loop():
    cases = _load_jsonl(CASE_DIR / "code_review_cases.jsonl")
    categories = {case["category"] for case in cases}

    assert {"project_audit", "change_review", "test_gap"}.issubset(categories)
    assert any("code_search" in case.get("required_tools", []) for case in cases)
    assert any("verification_runner" in case.get("required_tools", []) for case in cases)
    assert any(".git" in case["input"] for case in cases)
    assert any("不存在" in case["input"] for case in cases)
    assert not any(
        "git_inspector" in case.get("required_tools", [])
        for case in cases
        if case.get("judge_mode") == "real_smoke"
    )


def test_eval_cases_declare_judge_mode_and_failure_notes():
    allowed_modes = {"deterministic", "real_smoke", "manual_rubric"}

    for path in CASE_DIR.glob("*.jsonl"):
        for case in _load_jsonl(path):
            assert case.get("judge_mode") in allowed_modes, case["id"]
            assert case.get("failure_notes"), case["id"]


def test_real_smoke_cases_declare_expected_skill_and_trace():
    for path in CASE_DIR.glob("*.jsonl"):
        for case in _load_jsonl(path):
            if case.get("judge_mode") != "real_smoke":
                continue

            assert case.get("expected_skill"), case["id"]
            assert "skill_selected" in case.get("expected_trace_events", []), case["id"]


def test_code_review_real_smoke_cases_require_evidence_sections():
    cases = _load_jsonl(CASE_DIR / "code_review_cases.jsonl")
    real_smoke_cases = [
        case for case in cases if case.get("judge_mode") == "real_smoke"
    ]

    assert real_smoke_cases
    for case in real_smoke_cases:
        sections = set(case.get("expected_output_sections", []))
        assert sections & {"已读取文件", "Review Scope", "Verification"}, case["id"]
        assert sections & {"未确认事项", "Unconfirmed Items"}, case["id"]


def test_eval_cases_cover_boundaries_and_schema_design():
    runtime_cases = _load_jsonl(CASE_DIR / "runtime_cases.jsonl")
    eval_writer_cases = _load_jsonl(CASE_DIR / "eval_writer_cases.jsonl")
    context_cases = _load_jsonl(CASE_DIR / "context_cases.jsonl")

    assert any(case["category"] == "skill_selection_boundary" for case in runtime_cases)
    assert any("兼容当前 EvalCase schema" in case["input"] for case in eval_writer_cases)
    assert any("README" in case["input"] and "如果不存在" in case["input"] for case in context_cases)
    assert any("file_path 单文件读取" in case["input"] for case in eval_writer_cases)


def test_toolgateway_cases_explain_git_inspector_is_conditional():
    cases = _load_jsonl(CASE_DIR / "toolgateway_cases.jsonl")

    assert any("git_inspector" in case["input"] and ".git" in case["input"] for case in cases)
    assert all(
        "git_inspector" not in case.get("required_tools", [])
        for case in cases
    )
