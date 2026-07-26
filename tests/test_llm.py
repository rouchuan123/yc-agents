import unittest

import httpx
from openai import APIStatusError, APITimeoutError

from yc_agents.core.config import ProviderConfig
from yc_agents.core.exceptions import LLMCallError, TruncatedOutputError
from yc_agents.core.llm import YCAgentsLLM


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("upstream failed with key secret-key")


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self):
        self.chat = FakeChat()


class FakeDelta:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.delta = FakeDelta(content)


class FakeChunk:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class StreamingCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(
            [
                FakeChunk("hello"),
                FakeChunk(None),
                FakeChunk(" world"),
            ]
        )


class StreamingClient:
    def __init__(self):
        self.chat = FakeChat()
        self.chat.completions = StreamingCompletions()


class SuccessfulCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("Message", (), {"content": "ok"})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class SuccessfulClient:
    def __init__(self):
        self.chat = FakeChat()
        self.chat.completions = SuccessfulCompletions()


class FinishReasonCompletions:
    def __init__(self, content, finish_reason):
        self.calls = []
        self.content = content
        self.finish_reason = finish_reason

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("Message", (), {"content": self.content})()
        choice = type(
            "Choice",
            (),
            {"message": message, "finish_reason": self.finish_reason},
        )()
        return type("Response", (), {"choices": [choice]})()


class FinishReasonClient:
    def __init__(self, content, finish_reason):
        self.chat = FakeChat()
        self.chat.completions = FinishReasonCompletions(content, finish_reason)


class TestYCAgentsLLM(unittest.TestCase):
    def test_think_applies_ycore_request_defaults(self):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek-chat",
            api_key="secret-key",
            base_url="https://api.deepseek.com/v1",
            timeout=30,
            request_defaults={"max_tokens": 4096, "temperature": 0.2},
        )
        client = SuccessfulClient()
        llm = YCAgentsLLM(config=config, client=client)

        result = llm.think([{"role": "user", "content": "hello"}])

        self.assertEqual(result, "ok")
        call = client.chat.completions.calls[0]
        self.assertEqual(call["max_tokens"], 4096)
        self.assertEqual(call["temperature"], 0.2)

    def test_think_kwargs_override_ycore_request_defaults(self):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek-chat",
            api_key="secret-key",
            base_url="https://api.deepseek.com/v1",
            timeout=30,
            request_defaults={"max_tokens": 4096, "temperature": 0.2},
        )
        client = SuccessfulClient()
        llm = YCAgentsLLM(config=config, client=client)

        llm.think(
            [{"role": "user", "content": "hello"}],
            temperature=0.7,
        )

        call = client.chat.completions.calls[0]
        self.assertEqual(call["max_tokens"], 4096)
        self.assertEqual(call["temperature"], 0.7)

    def test_think_json_applies_structured_output_defaults(self):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="secret-key",
            base_url="https://api.deepseek.com",
            request_defaults={"temperature": 0.2},
            json_request_defaults={"response_format": {"type": "json_object"}},
        )
        client = SuccessfulClient()
        llm = YCAgentsLLM(config=config, client=client)

        llm.think_json([{"role": "user", "content": "return json"}])

        call = client.chat.completions.calls[0]
        self.assertEqual(call["temperature"], 0.2)
        self.assertEqual(call["response_format"], {"type": "json_object"})

    def test_think_json_kwargs_override_structured_output_defaults(self):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="secret-key",
            base_url="https://api.deepseek.com",
            json_request_defaults={"response_format": {"type": "json_object"}},
        )
        client = SuccessfulClient()
        llm = YCAgentsLLM(config=config, client=client)

        llm.think_json(
            [{"role": "user", "content": "return json"}],
            response_format={"type": "text"},
        )

        call = client.chat.completions.calls[0]
        self.assertEqual(call["response_format"], {"type": "text"})

    def test_think_wraps_provider_error_without_leaking_api_key(self):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek-chat",
            api_key="secret-key",
            base_url="https://api.deepseek.com/v1",
            timeout=30,
        )
        llm = YCAgentsLLM(config=config, client=FakeClient())

        with self.assertRaises(LLMCallError) as context:
            llm.think([{"role": "user", "content": "你好"}])

        message = str(context.exception)
        self.assertIn("deepseek", message)
        self.assertIn("deepseek-chat", message)
        self.assertIn("模型调用失败", message)
        self.assertNotIn("secret-key", message)
        self.assertIsInstance(context.exception.__cause__, RuntimeError)
        self.assertFalse(context.exception.retryable)
        self.assertEqual(context.exception.cause_type, "RuntimeError")

    def test_timeout_error_is_marked_retryable(self):
        llm = YCAgentsLLM(
            config=ProviderConfig(
                provider="deepseek",
                model="deepseek-chat",
                api_key="secret-key",
                base_url="https://api.deepseek.com/v1",
            ),
            client=SuccessfulClient(),
        )
        provider_error = APITimeoutError(
            request=httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions")
        )

        with self.assertRaises(LLMCallError) as context:
            llm._raise_call_error(provider_error)

        self.assertTrue(context.exception.retryable)
        self.assertEqual(context.exception.cause_type, "APITimeoutError")

    def test_provider_4xx_is_not_marked_retryable(self):
        llm = YCAgentsLLM(
            config=ProviderConfig(
                provider="deepseek",
                model="deepseek-chat",
                api_key="secret-key",
                base_url="https://api.deepseek.com/v1",
            ),
            client=SuccessfulClient(),
        )
        request = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions")
        provider_error = APIStatusError(
            "bad request",
            response=httpx.Response(400, request=request),
            body=None,
        )

        with self.assertRaises(LLMCallError) as context:
            llm._raise_call_error(provider_error)

        self.assertFalse(context.exception.retryable)
        self.assertEqual(context.exception.status_code, 400)

    def test_think_raises_truncated_output_error_when_finish_reason_is_length(self):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek-chat",
            api_key="secret-key",
            base_url="https://api.deepseek.com/v1",
            timeout=30,
            request_defaults={"max_tokens": 4096},
        )
        client = FinishReasonClient('{"type":"final_answer","content":"部分', "length")
        llm = YCAgentsLLM(config=config, client=client)

        with self.assertRaises(TruncatedOutputError) as context:
            llm.think([{"role": "user", "content": "写一篇长报告"}])

        self.assertEqual(context.exception.max_tokens, 4096)
        self.assertIn("部分", context.exception.partial_text)
        self.assertTrue(context.exception.retryable)
        self.assertIn("max_tokens", str(context.exception))

    def test_think_json_reports_truncation_from_max_completion_tokens_key(self):
        config = ProviderConfig(
            provider="xiaomi",
            model="mimo-v2.5",
            api_key="secret-key",
            base_url="https://api.xiaomimimo.com/v1",
            timeout=30,
            request_defaults={"max_completion_tokens": 2048},
        )
        client = FinishReasonClient("partial json", "length")
        llm = YCAgentsLLM(config=config, client=client)

        with self.assertRaises(TruncatedOutputError) as context:
            llm.think_json([{"role": "user", "content": "return json"}])

        self.assertEqual(context.exception.max_tokens, 2048)
        self.assertEqual(context.exception.partial_text, "partial json")

    def test_truncated_output_error_stays_compatible_with_llm_call_error_handlers(self):
        self.assertTrue(issubclass(TruncatedOutputError, LLMCallError))

    def test_think_returns_content_when_finish_reason_is_stop(self):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek-chat",
            api_key="secret-key",
            base_url="https://api.deepseek.com/v1",
            timeout=30,
            request_defaults={"max_tokens": 4096},
        )
        client = FinishReasonClient("ok", "stop")
        llm = YCAgentsLLM(config=config, client=client)

        result = llm.think([{"role": "user", "content": "hello"}])

        self.assertEqual(result, "ok")

    def test_call_overrides_beat_request_defaults_until_cleared(self):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek-chat",
            api_key="secret-key",
            base_url="https://api.deepseek.com/v1",
            timeout=30,
            request_defaults={"max_tokens": 4096, "temperature": 0.2},
        )
        client = SuccessfulClient()
        llm = YCAgentsLLM(config=config, client=client)

        llm.set_call_overrides(max_tokens=8192)
        llm.think([{"role": "user", "content": "hello"}])
        llm.clear_call_overrides()
        llm.think([{"role": "user", "content": "hello"}])

        calls = client.chat.completions.calls
        self.assertEqual(calls[0]["max_tokens"], 8192)
        self.assertEqual(calls[0]["temperature"], 0.2)
        self.assertEqual(calls[1]["max_tokens"], 4096)

    def test_call_override_max_tokens_lands_on_max_completion_tokens_key(self):
        config = ProviderConfig(
            provider="xiaomi",
            model="mimo-v2.5",
            api_key="secret-key",
            base_url="https://api.xiaomimimo.com/v1",
            timeout=30,
            request_defaults={"max_completion_tokens": 4096},
        )
        client = SuccessfulClient()
        llm = YCAgentsLLM(config=config, client=client)

        llm.set_call_overrides(max_tokens=8192)
        llm.think([{"role": "user", "content": "hello"}])

        call = client.chat.completions.calls[0]
        self.assertEqual(call["max_completion_tokens"], 8192)
        self.assertNotIn("max_tokens", call)

    def test_think_json_per_call_max_tokens_overrides_defaults(self):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="secret-key",
            base_url="https://api.deepseek.com",
            request_defaults={"max_tokens": 4096},
            json_request_defaults={"response_format": {"type": "json_object"}},
        )
        client = SuccessfulClient()
        llm = YCAgentsLLM(config=config, client=client)

        llm.think_json(
            [{"role": "user", "content": "return json"}],
            max_tokens=1024,
        )

        call = client.chat.completions.calls[0]
        self.assertEqual(call["max_tokens"], 1024)
        self.assertEqual(call["response_format"], {"type": "json_object"})

    def test_stream_think_yields_delta_content(self):
        config = ProviderConfig(
            provider="deepseek",
            model="deepseek-chat",
            api_key="secret-key",
            base_url="https://api.deepseek.com/v1",
            timeout=30,
            request_defaults={"max_tokens": 4096, "temperature": 0.2},
        )
        client = StreamingClient()
        llm = YCAgentsLLM(config=config, client=client)

        chunks = list(llm.stream_think([{"role": "user", "content": "hello"}]))

        self.assertEqual(chunks, ["hello", " world"])
        call = client.chat.completions.calls[0]
        self.assertEqual(call["max_tokens"], 4096)
        self.assertEqual(call["temperature"], 0.2)
        self.assertTrue(call["stream"])


if __name__ == "__main__":
    unittest.main()
