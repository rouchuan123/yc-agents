import unittest

from yc_agents.core.config import ProviderConfig
from yc_agents.core.exceptions import LLMCallError
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
