import json

from yc_agents.core.usage import TokenUsage
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.harness.token_budget import TokenBudget, TokenBudgetPolicy
from yc_agents.tools.base import BaseTool
from yc_agents.tools.registry import ToolRegistry


def test_token_budget_estimates_text_and_flags_over_budget():
    budget = TokenBudget(max_tokens=10)

    budget.add("memory", "a " * 20)

    assert budget.total_estimated_tokens > 0
    assert budget.is_over_budget()


def test_token_budget_breakdown():
    budget = TokenBudget(max_tokens=100)
    budget.add("skill_summary", "abc")

    assert budget.breakdown()["skill_summary"] > 0


def test_token_budget_tracks_sections_and_remaining_tokens():
    budget = TokenBudget(max_tokens=10)
    budget.add("memory", "abcdefgh")
    budget.add("memory", "ijkl")
    budget.add("skills", "mnop")

    assert budget.breakdown()["memory"] == 3
    assert budget.breakdown()["skills"] == 1
    assert budget.remaining_tokens == 6
    assert budget.is_over_budget() is False


def test_token_budget_marks_exact_limit_as_over_budget():
    budget = TokenBudget(max_tokens=1)
    budget.add("input", "abcd")

    assert budget.remaining_tokens == 0
    assert budget.is_over_budget() is True


class EchoTool(BaseTool):
    name = "fake_tool"
    description = "Fake tool."

    def run(self, text):
        return {"echo": text}


class FakeLedger:
    def __init__(self):
        self.session_totals = TokenUsage()

    def consume(self, input_tokens=0, output_tokens=0, cached_tokens=0):
        self.session_totals.add(
            TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cached_tokens=cached_tokens,
            )
        )


class FakeLLM:
    def __init__(self, usage_ledger):
        self.usage_ledger = usage_ledger


class ScriptedBudgetAgent:
    def __init__(self, responses, ledger=None, call_usage=None):
        self.responses = list(responses)
        self.ledger = ledger
        self.call_usage = dict(call_usage or {})
        self.observations = []
        if ledger is not None:
            self.llm = FakeLLM(ledger)

    def _reply(self):
        if self.ledger is not None and self.call_usage:
            self.ledger.consume(**self.call_usage)
        return self.responses.pop(0)

    def run(self, user_input):
        return self._reply()

    def run_with_observation(self, user_input, observation):
        self.observations.append(observation)
        return self._reply()


class FakeRunAnalytics:
    strict = True

    def __init__(self):
        self.token_usages = []
        self.finishes = []

    def record_event(self, event):
        return None

    def record_verification(self, verification):
        return None

    def record_final_output(self, output):
        return None

    def record_token_usage(self, usage):
        self.token_usages.append(dict(usage))

    def finish(self, status, finished_at=None, error_type=None, error_message=None):
        self.finishes.append(status)


class FakeAnalyticsRecorder:
    def __init__(self):
        self.run = FakeRunAnalytics()

    def start_run(self, context):
        return self.run

    def close(self):
        return None


def _tool_call(text="hello"):
    return json.dumps(
        {
            "type": "tool_call",
            "tool_name": "fake_tool",
            "arguments": {"text": text},
            "reason": "test",
        }
    )


def _final_answer(content="done"):
    return json.dumps({"type": "final_answer", "content": content})


def _build_runtime(agent, tmp_path, policy=None, analytics_recorder=None):
    registry = ToolRegistry()
    registry.register(EchoTool())
    return YCAgentRuntime(
        agent,
        expects_json=True,
        tool_registry=registry,
        allowed_tools=["fake_tool"],
        output_root=tmp_path,
        token_budget_policy=policy,
        analytics_recorder=analytics_recorder,
    )


def _events_of(runtime, event_type):
    return [
        event
        for event in runtime.last_trace_events
        if event["event_type"] == event_type
    ]


def test_token_budget_policy_disabled_without_limits():
    policy = TokenBudgetPolicy()

    assert policy.enabled is False
    assert policy.start_meter(FakeLedger()) is None


def test_token_budget_policy_from_runtime_config_reads_token_budget_section():
    policy = TokenBudgetPolicy.from_runtime_config(
        {"tokenBudget": {"softTokens": 1500, "hardTokens": 3000}}
    )

    assert policy.soft_limit_tokens == 1500
    assert policy.hard_limit_tokens == 3000
    assert policy.enabled is True
    assert TokenBudgetPolicy.from_runtime_config({}).enabled is False
    assert TokenBudgetPolicy.from_runtime_config(None).enabled is False


def test_token_budget_meter_measures_run_delta_and_fires_soft_once():
    ledger = FakeLedger()
    ledger.consume(input_tokens=500)
    policy = TokenBudgetPolicy(soft_limit_tokens=50)
    meter = policy.start_meter(ledger)

    assert meter.check() is None

    ledger.consume(input_tokens=60, output_tokens=40)

    status = meter.check()
    assert status == {"level": "soft", "run_tokens": 100, "limit": 50}
    assert meter.check() is None


def test_token_budget_meter_hard_limit_keeps_firing():
    ledger = FakeLedger()
    policy = TokenBudgetPolicy(soft_limit_tokens=10, hard_limit_tokens=80)
    meter = policy.start_meter(ledger)
    ledger.consume(input_tokens=100)

    first = meter.check()
    second = meter.check()

    assert first["level"] == "hard"
    assert first["limit"] == 80
    assert second["level"] == "hard"


def test_token_budget_meter_disabled_without_ledger():
    policy = TokenBudgetPolicy(soft_limit_tokens=10)

    assert policy.start_meter(None) is None


def test_runtime_soft_limit_injects_one_time_convergence_notice(tmp_path):
    ledger = FakeLedger()
    agent = ScriptedBudgetAgent(
        [_tool_call("first"), _tool_call("second"), _final_answer()],
        ledger=ledger,
        call_usage={"input_tokens": 60, "output_tokens": 40},
    )
    runtime = _build_runtime(
        agent,
        tmp_path,
        policy=TokenBudgetPolicy(soft_limit_tokens=50),
    )

    result = runtime.run("do work")

    assert str(result) == "done"
    assert "收敛" in agent.observations[0]["budget_notice"]
    assert "budget_notice" not in agent.observations[1]
    assert len(_events_of(runtime, "budget_soft_exceeded")) == 1
    assert _events_of(runtime, "budget_hard_exceeded") == []


def test_runtime_hard_limit_stops_run_and_keeps_partial_result(tmp_path):
    ledger = FakeLedger()
    recorder = FakeAnalyticsRecorder()
    agent = ScriptedBudgetAgent(
        [_tool_call("first")],
        ledger=ledger,
        call_usage={"input_tokens": 60, "output_tokens": 40, "cached_tokens": 5},
    )
    runtime = _build_runtime(
        agent,
        tmp_path,
        policy=TokenBudgetPolicy(soft_limit_tokens=30, hard_limit_tokens=80),
        analytics_recorder=recorder,
    )

    result = runtime.run("do work")

    assert result.status == "stopped"
    assert result.stop_reason["error_type"] == "token_budget_exhausted"
    assert "任务未能完整完成" in str(result)
    assert agent.observations == []
    assert len(_events_of(runtime, "budget_hard_exceeded")) == 1
    assert recorder.run.finishes == ["failed"]
    assert recorder.run.token_usages == [
        {
            "input_tokens": 60,
            "output_tokens": 40,
            "cached_tokens": 5,
            "total_tokens": 100,
        }
    ]


def test_runtime_budget_silently_disabled_without_usage_ledger(tmp_path):
    agent = ScriptedBudgetAgent([_tool_call("first"), _final_answer()])
    runtime = _build_runtime(
        agent,
        tmp_path,
        policy=TokenBudgetPolicy(soft_limit_tokens=1, hard_limit_tokens=2),
    )

    result = runtime.run("do work")

    assert str(result) == "done"
    assert _events_of(runtime, "budget_soft_exceeded") == []
    assert _events_of(runtime, "budget_hard_exceeded") == []


def test_runtime_records_run_level_token_delta_to_analytics(tmp_path):
    ledger = FakeLedger()
    ledger.consume(input_tokens=900, output_tokens=100)
    recorder = FakeAnalyticsRecorder()
    agent = ScriptedBudgetAgent(
        [_tool_call("first"), _final_answer()],
        ledger=ledger,
        call_usage={"input_tokens": 60, "output_tokens": 40, "cached_tokens": 10},
    )
    runtime = _build_runtime(agent, tmp_path, analytics_recorder=recorder)

    runtime.run("do work")

    assert recorder.run.token_usages == [
        {
            "input_tokens": 120,
            "output_tokens": 80,
            "cached_tokens": 20,
            "total_tokens": 200,
        }
    ]
