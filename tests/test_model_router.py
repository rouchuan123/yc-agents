import tempfile
import unittest
from pathlib import Path

from yc_agents.core.exceptions import (
    LLMCallError,
    ToolCallingUnsupportedError,
    TruncatedOutputError,
)
from yc_agents.core.model_router import ModelRouter
from yc_agents.core.usage import UsageLedger
from yc_agents.harness.runtime import YCAgentRuntime


class ScriptedLLM:
    def __init__(self, model, results=None, json_results=None):
        self.model = model
        self.provider = f"{model}-provider"
        self.config = type("Config", (), {"max_output_tokens": 4096})()
        self.client = object()
        self.usage_ledger = UsageLedger()
        self.last_primary_messages = []
        self.results = list(results or [])
        self.json_results = list(json_results or [])
        self.calls = []
        self.override_calls = []
        self.clear_calls = 0

    def _next(self, results):
        outcome = results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def think(self, messages, usage_kind="primary", **kwargs):
        self.calls.append({"messages": messages, "usage_kind": usage_kind, **kwargs})
        return self._next(self.results)

    def think_json(self, messages, usage_kind="primary", **kwargs):
        self.calls.append({"messages": messages, "usage_kind": usage_kind, **kwargs})
        return self._next(self.json_results)

    def stream_think(self, messages, usage_kind="primary", **kwargs):
        yield self._next(self.results)

    def set_call_overrides(self, **overrides):
        self.override_calls.append(dict(overrides))

    def clear_call_overrides(self):
        self.clear_calls += 1


def retryable_error(message="provider unavailable"):
    return LLMCallError(
        message,
        retryable=True,
        status_code=503,
        cause_type="APIConnectionError",
    )


class TestModelRouter(unittest.TestCase):
    def build_router(self, primary, fallback, retries_per_model=1):
        sleeps = []
        router = ModelRouter(
            [primary, fallback],
            retries_per_model=retries_per_model,
            backoff_seconds=0.5,
            sleep=sleeps.append,
        )
        return router, sleeps

    def test_requires_at_least_one_llm(self):
        with self.assertRaisesRegex(ValueError, "至少一个"):
            ModelRouter([])

    def test_primary_success_stays_on_primary_without_switch(self):
        primary = ScriptedLLM("primary-model", ["primary answer"])
        fallback = ScriptedLLM("fallback-model", ["unused"])
        router, sleeps = self.build_router(primary, fallback)

        result = router.think([{"role": "user", "content": "hi"}], usage_kind="primary")

        self.assertEqual(result, "primary answer")
        self.assertEqual(router.model, "primary-model")
        self.assertEqual(router.switch_events, [])
        self.assertEqual(router.consume_switch_events(), [])
        self.assertEqual(fallback.calls, [])
        self.assertEqual(sleeps, [])

    def test_retry_exhaustion_switches_to_fallback_and_records_event(self):
        primary = ScriptedLLM(
            "primary-model",
            [retryable_error(), retryable_error()],
        )
        fallback = ScriptedLLM("fallback-model", ["fallback answer"])
        router, sleeps = self.build_router(primary, fallback, retries_per_model=1)

        result = router.think([{"role": "user", "content": "hi"}])

        self.assertEqual(result, "fallback answer")
        self.assertEqual(len(primary.calls), 2)
        self.assertEqual(len(fallback.calls), 1)
        self.assertEqual(sleeps, [0.5])
        self.assertEqual(len(router.switch_events), 1)
        event = router.switch_events[0]
        self.assertEqual(event["from_model"], "primary-model")
        self.assertEqual(event["to_model"], "fallback-model")
        self.assertEqual(event["error_type"], "APIConnectionError")
        # 切换后保持粘性：后续读取到的活跃模型是 fallback。
        self.assertEqual(router.model, "fallback-model")

    def test_consume_switch_events_drains_pending_events_once(self):
        primary = ScriptedLLM(
            "primary-model",
            [retryable_error(), retryable_error()],
        )
        fallback = ScriptedLLM("fallback-model", ["fallback answer"])
        router, _sleeps = self.build_router(primary, fallback)

        router.think([{"role": "user", "content": "hi"}])

        drained = router.consume_switch_events()
        self.assertEqual(len(drained), 1)
        self.assertEqual(router.consume_switch_events(), [])
        # 全量历史仍然保留，便于诊断。
        self.assertEqual(len(router.switch_events), 1)

    def test_sticky_fallback_serves_next_call_without_touching_primary(self):
        primary = ScriptedLLM(
            "primary-model",
            [retryable_error(), retryable_error()],
        )
        fallback = ScriptedLLM("fallback-model", ["first", "second"])
        router, _sleeps = self.build_router(primary, fallback)

        router.think([{"role": "user", "content": "one"}])
        result = router.think([{"role": "user", "content": "two"}])

        self.assertEqual(result, "second")
        self.assertEqual(len(primary.calls), 2)
        self.assertEqual(len(fallback.calls), 2)

    def test_full_chain_exhaustion_raises_teaching_error_and_resets_chain(self):
        primary = ScriptedLLM(
            "primary-model",
            [retryable_error(), retryable_error(), "recovered"],
        )
        fallback = ScriptedLLM(
            "fallback-model",
            [retryable_error("fallback down"), retryable_error("fallback down")],
        )
        router, _sleeps = self.build_router(primary, fallback)

        with self.assertRaises(LLMCallError) as ctx:
            router.think([{"role": "user", "content": "hi"}])

        message = str(ctx.exception)
        self.assertIn("primary-model", message)
        self.assertIn("fallback-model", message)
        self.assertIn("fallbacks", message)
        self.assertTrue(ctx.exception.retryable)
        # 链路耗尽后回到主模型，下一次调用重新从头走整条链。
        result = router.think([{"role": "user", "content": "again"}])
        self.assertEqual(result, "recovered")
        self.assertEqual(router.model, "primary-model")

    def test_truncated_output_error_passes_through_without_switch(self):
        primary = ScriptedLLM(
            "primary-model",
            [TruncatedOutputError("truncated", partial_text="partial", max_tokens=64)],
        )
        fallback = ScriptedLLM("fallback-model", ["unused"])
        router, sleeps = self.build_router(primary, fallback)

        with self.assertRaises(TruncatedOutputError):
            router.think([{"role": "user", "content": "hi"}])

        self.assertEqual(fallback.calls, [])
        self.assertEqual(router.switch_events, [])
        self.assertEqual(sleeps, [])

    def test_non_retryable_error_passes_through_for_native_fc_fallback(self):
        primary = ScriptedLLM(
            "primary-model",
            [ToolCallingUnsupportedError("tools rejected", status_code=400)],
        )
        fallback = ScriptedLLM("fallback-model", ["unused"])
        router, _sleeps = self.build_router(primary, fallback)

        with self.assertRaises(ToolCallingUnsupportedError):
            router.think(
                [{"role": "user", "content": "hi"}],
                tools=[{"type": "function"}],
            )

        self.assertEqual(fallback.calls, [])
        self.assertEqual(router.switch_events, [])

    def test_think_json_routes_through_same_fallback_chain(self):
        primary = ScriptedLLM(
            "primary-model",
            json_results=[retryable_error(), retryable_error()],
        )
        fallback = ScriptedLLM("fallback-model", json_results=['{"ok": true}'])
        router, _sleeps = self.build_router(primary, fallback)

        result = router.think_json([{"role": "user", "content": "hi"}])

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(len(router.switch_events), 1)

    def test_call_overrides_propagate_to_every_chain_member(self):
        primary = ScriptedLLM("primary-model", ["ok"])
        fallback = ScriptedLLM("fallback-model", ["ok"])
        router, _sleeps = self.build_router(primary, fallback)

        router.set_call_overrides(max_tokens=8192)
        router.clear_call_overrides()

        self.assertEqual(primary.override_calls, [{"max_tokens": 8192}])
        self.assertEqual(fallback.override_calls, [{"max_tokens": 8192}])
        self.assertEqual(primary.clear_calls, 1)
        self.assertEqual(fallback.clear_calls, 1)

    def test_set_usage_path_targets_shared_ledger(self):
        primary = ScriptedLLM("primary-model", ["ok"])
        fallback = ScriptedLLM("fallback-model", ["ok"])
        fallback.usage_ledger = primary.usage_ledger
        router, _sleeps = self.build_router(primary, fallback)

        with tempfile.TemporaryDirectory() as tmp_dir:
            usage_path = Path(tmp_dir) / "usage.json"
            ledger = router.set_usage_path(usage_path)

            self.assertIs(ledger, primary.usage_ledger)
            self.assertEqual(primary.usage_ledger.file_path, usage_path)

    def test_router_exposes_active_model_attributes(self):
        primary = ScriptedLLM("primary-model", [retryable_error(), retryable_error()])
        fallback = ScriptedLLM("fallback-model", ["ok"])
        router, _sleeps = self.build_router(primary, fallback)

        self.assertIs(router.config, primary.config)
        self.assertIs(router.client, primary.client)
        self.assertEqual(router.provider, "primary-model-provider")
        self.assertIs(router.usage_ledger, primary.usage_ledger)

        router.think([{"role": "user", "content": "hi"}])

        self.assertIs(router.config, fallback.config)
        self.assertIs(router.client, fallback.client)
        self.assertEqual(router.provider, "fallback-model-provider")
        # usage_ledger 始终指向主模型的共享账本。
        self.assertIs(router.usage_ledger, primary.usage_ledger)


class SwitchingAgent:
    """Fake agent whose llm switches once and exposes consume_switch_events."""

    def __init__(self):
        self.llm = _SwitchingLLM()

    def run(self, user_input):
        return f"echo: {user_input}"


class _SwitchingLLM:
    model = "fallback-model"

    def __init__(self):
        self._pending = [
            {
                "from_model": "primary-model",
                "to_model": "fallback-model",
                "error_type": "APIConnectionError",
            }
        ]

    def consume_switch_events(self):
        drained = list(self._pending)
        self._pending = []
        return drained


class TestModelSwitchTraceEvents(unittest.TestCase):
    def test_runtime_records_model_switched_trace_event(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = YCAgentRuntime(
                SwitchingAgent(),
                output_root=Path(tmp_dir) / "runs",
            )

            result = runtime.run("hello")

            self.assertEqual(str(result), "echo: hello")
            switch_events = [
                event
                for event in runtime.last_trace_events
                if event["event_type"] == "model_switched"
            ]
            self.assertEqual(len(switch_events), 1)
            self.assertEqual(
                switch_events[0]["payload"]["to_model"],
                "fallback-model",
            )


if __name__ == "__main__":
    unittest.main()
