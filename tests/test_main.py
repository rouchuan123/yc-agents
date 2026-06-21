import unittest
from unittest.mock import patch

import main
from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.session import SessionMemory
from yc_agents.tools.markdown_writer import MarkdownWriterTool


class FakeLLM:
    pass


class TestMainEntryPoint(unittest.TestCase):
    @patch("main.YCAgentsLLM", return_value=FakeLLM())
    def test_build_runtime_wraps_skill_runtime_agent(self, _mock_llm_class):
        runtime = main.build_runtime()

        self.assertIsInstance(runtime, YCAgentRuntime)
        self.assertIsInstance(runtime.agent, SkillRuntimeAgent)

    @patch("main.YCAgentsLLM", return_value=FakeLLM())
    def test_build_runtime_registers_markdown_writer_tool(self, _mock_llm_class):
        runtime = main.build_runtime()

        self.assertTrue(runtime.expects_json)
        self.assertIn("markdown_writer", runtime.allowed_tools)
        self.assertIsInstance(
            runtime.tool_registry.get_tool("markdown_writer"),
            MarkdownWriterTool,
        )

    @patch("main.YCAgentsLLM", return_value=FakeLLM())
    def test_build_runtime_configures_session_memory(self, _mock_llm_class):
        runtime = main.build_runtime()

        self.assertIsInstance(runtime.agent.session_memory, SessionMemory)


if __name__ == "__main__":
    unittest.main()
