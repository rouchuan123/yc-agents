import unittest

from yc_agents.core.config import ProviderConfig
from yc_agents.core.exceptions import LLMCallError
from yc_agents.core.llm import YCAgentsLLM


class FakeCompletions:
    def create(self, **kwargs):
        raise RuntimeError("upstream failed with key secret-key")


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self):
        self.chat = FakeChat()


class TestYCAgentsLLM(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
