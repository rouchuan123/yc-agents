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
                "input": "总结资料中的接口问题",
                "expected_keywords": ["接口问题"],
                "required_tools": ["rag_search"],
                "reference_sources": ["code-notes.md"],
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
            input="总结资料中的接口问题",
            expected_keywords=["接口问题"],
            required_tools=["rag_search"],
            reference_sources=["code-notes.md"],
        )
    ]


def test_load_cases_accepts_trace_expectations(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "tool-allowed-001",
                "category": "tool_use",
                "input": "列出工作区文件",
                "expected_keywords": ["文件"],
                "required_tools": ["workspace_files"],
                "expected_trace_events": ["tool_called"],
                "forbidden_tools": ["web_search"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_cases(path)

    assert cases[0].expected_trace_events == ["tool_called"]
    assert cases[0].forbidden_tools == ["web_search"]


class FakeRuntime:
    def run(self, user_input):
        return f"接口问题 技术路线 output for {user_input}"


def test_run_cases_with_fake_runtime():
    case = EvalCase(
        id="case-1",
        category="opening_report",
        input="写开题大纲",
        expected_keywords=["接口问题", "技术路线"],
    )

    results = run_cases(FakeRuntime(), [case])

    assert results[0]["case_id"] == "case-1"
    assert results[0]["keyword_success"] is True
    assert results[0]["latency_seconds"] >= 0


class FakeTraceRuntime:
    def __init__(self):
        self.last_trace_events = [
            {"event_type": "tool_called", "payload": {"tool_name": "workspace_files"}},
        ]

    def run(self, user_input):
        return f"文件 output for {user_input}"


def test_run_cases_includes_trace_metrics():
    case = EvalCase(
        id="case-1",
        category="tool_use",
        input="列出工作区文件",
        expected_keywords=["文件"],
        required_tools=["workspace_files"],
        expected_trace_events=["tool_called"],
        forbidden_tools=["web_search"],
    )

    results = run_cases(FakeTraceRuntime(), [case])

    assert results[0]["tool_success"] is True
    assert results[0]["trace_event_success"] is True
    assert results[0]["forbidden_tool_success"] is True


class FakeAnalyticsRecorder:
    def __init__(self):
        self.eval_results = []

    def record_eval_result(self, result):
        self.eval_results.append(result)


def test_run_cases_records_eval_results_when_runtime_has_analytics():
    class FakeAnalyticsRuntime:
        def __init__(self):
            self.analytics_recorder = FakeAnalyticsRecorder()
            self.last_run_id = None
            self.last_trace_events = [
                {"event_type": "tool_called", "payload": {"tool_name": "workspace_files"}},
            ]

        def run(self, user_input):
            self.last_run_id = "run-analytics-1"
            return f"文件 output for {user_input}"

    runtime = FakeAnalyticsRuntime()

    results = run_cases(
        runtime,
        [
            EvalCase(
                id="case-1",
                category="skill_selection",
                input="hello",
                expected_keywords=["文件"],
                required_tools=["workspace_files"],
            )
        ],
    )

    assert len(results) == 1
    assert runtime.analytics_recorder.eval_results[0]["case_id"] == "case-1"
    assert runtime.analytics_recorder.eval_results[0]["run_id"] == runtime.last_run_id
