import unittest

from yc_agents.core.provider import get_provider_capabilities


class TestProviderCapabilities(unittest.TestCase):
    def test_openai_capabilities_include_json_and_tool_calling(self):
        capabilities = get_provider_capabilities("openai")

        self.assertTrue(capabilities["json_output"])
        self.assertTrue(capabilities["tool_calling"])
        self.assertTrue(capabilities["long_context"])

    def test_ollama_capabilities_do_not_assume_tool_calling(self):
        capabilities = get_provider_capabilities("ollama")

        self.assertTrue(capabilities["json_output"])
        self.assertFalse(capabilities["tool_calling"])
        self.assertFalse(capabilities["long_context"])

    def test_unknown_provider_uses_openai_compatible_defaults(self):
        capabilities = get_provider_capabilities("unknown-provider")

        self.assertEqual(capabilities["provider"], "openai_compatible")
        self.assertTrue(capabilities["json_output"])
        self.assertFalse(capabilities["tool_calling"])

    def test_capabilities_are_returned_as_copy(self):
        capabilities = get_provider_capabilities("deepseek")
        capabilities["json_output"] = False

        fresh_capabilities = get_provider_capabilities("deepseek")

        self.assertTrue(fresh_capabilities["json_output"])


if __name__ == "__main__":
    unittest.main()
