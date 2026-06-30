import unittest

from yc_agents.config.ycore import ModelProviderSettings
from yc_agents.core.config import ProviderConfig


class TestProviderConfig(unittest.TestCase):
    def test_from_env_reads_required_llm_settings(self):
        env = {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL_ID": "gpt-test",
            "LLM_API_KEY": "secret-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_TIMEOUT": "45",
        }

        config = ProviderConfig.from_env(env)

        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.model, "gpt-test")
        self.assertEqual(config.api_key, "secret-key")
        self.assertEqual(config.base_url, "https://api.openai.com/v1")
        self.assertEqual(config.timeout, 45)

    def test_from_env_auto_detects_provider_from_base_url(self):
        env = {
            "LLM_PROVIDER": "auto",
            "LLM_MODEL_ID": "deepseek-chat",
            "LLM_API_KEY": "secret-key",
            "LLM_BASE_URL": "https://api.deepseek.com/v1",
        }

        config = ProviderConfig.from_env(env)

        self.assertEqual(config.provider, "deepseek")
        self.assertTrue(config.capabilities["json_output"])

    def test_to_safe_dict_includes_capabilities(self):
        env = {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL_ID": "gpt-test",
            "LLM_API_KEY": "secret-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
        }

        config = ProviderConfig.from_env(env)
        result = config.to_safe_dict()

        self.assertEqual(
            result["capabilities"],
            {
                "provider": "openai",
                "json_output": True,
                "tool_calling": True,
                "long_context": True,
            },
        )

    def test_to_safe_dict_hides_api_key(self):
        config = ProviderConfig(
            provider="modelscope",
            model="qwen-test",
            api_key="real-secret",
            base_url="https://api-inference.modelscope.cn/v1",
            timeout=60,
        )

        result = config.to_safe_dict()

        self.assertEqual(
            result,
            {
                "provider": "modelscope",
                "model": "qwen-test",
                "base_url": "https://api-inference.modelscope.cn/v1",
                "timeout": 60,
                "context_window": None,
                "max_output_tokens": None,
                "request_defaults": {},
                "json_request_defaults": {},
                "has_api_key": True,
                "capabilities": {
                    "provider": "modelscope",
                    "json_output": True,
                    "tool_calling": True,
                    "long_context": True,
                },
            },
        )
        self.assertNotIn("api_key", result)
        self.assertNotIn("real-secret", str(result))

    def test_missing_required_setting_raises_clear_error(self):
        env = {
            "LLM_PROVIDER": "openai",
            "LLM_API_KEY": "secret-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
        }

        with self.assertRaisesRegex(ValueError, "缺少 LLM_MODEL_ID"):
            ProviderConfig.from_env(env)

    def test_invalid_timeout_raises_clear_error(self):
        env = {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL_ID": "gpt-test",
            "LLM_API_KEY": "secret-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_TIMEOUT": "not-a-number",
        }

        with self.assertRaisesRegex(ValueError, "LLM_TIMEOUT 必须是正整数"):
            ProviderConfig.from_env(env)

    def test_zero_timeout_raises_clear_error(self):
        env = {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL_ID": "gpt-test",
            "LLM_API_KEY": "secret-key",
            "LLM_BASE_URL": "https://api.openai.com/v1",
            "LLM_TIMEOUT": "0",
        }

        with self.assertRaisesRegex(ValueError, "LLM_TIMEOUT 必须是正整数"):
            ProviderConfig.from_env(env)

    def test_provider_config_can_be_created_from_ycore_settings(self):
        settings = ModelProviderSettings(
            provider="deepseek",
            model="deepseek-v4-flash",
            api="openai-completions",
            base_url="https://api.deepseek.com",
            api_key="secret",
            timeout=45,
            context_window=64000,
            max_output_tokens=4096,
            request={"max_tokens": 4096, "temperature": 0.2},
            structured_output_request={
                "response_format": {"type": "json_object"},
            },
        )

        config = ProviderConfig.from_ycore(settings)

        self.assertEqual(config.provider, "deepseek")
        self.assertEqual(config.model, "deepseek-v4-flash")
        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.base_url, "https://api.deepseek.com")
        self.assertEqual(config.timeout, 45)
        self.assertEqual(config.context_window, 64000)
        self.assertEqual(config.max_output_tokens, 4096)
        self.assertEqual(config.request_defaults, {"max_tokens": 4096, "temperature": 0.2})
        self.assertEqual(
            config.json_request_defaults,
            {"response_format": {"type": "json_object"}},
        )


if __name__ == "__main__":
    unittest.main()
