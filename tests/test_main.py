import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.cli.workspaces import WorkspaceStore
from yc_agents.harness.permissions import HumanApprovalGate
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.compressor import MemoryCompressor
from yc_agents.memory.profile import ResearchProfileMemory
from yc_agents.memory.session import SessionMemory
from yc_agents.memory.summary import SummaryMemory
from yc_agents.tools.docx_reader import DocxReaderTool
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.mcp_adapter import MCPToolAdapter
from yc_agents.tools.rag_search import RAGSearchTool


class FakeLLM:
    pass


class TestMainEntryPoint(unittest.TestCase):
    def build_runtime_in_temp_workspace(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        with patch(
            "main.WorkspaceStore",
            side_effect=lambda: WorkspaceStore(ycore_root=root, startup_dir=root),
        ):
            return main.build_runtime()

    @patch("main.YCAgentsLLM", return_value=FakeLLM())
    def test_build_runtime_wraps_skill_runtime_agent(self, _mock_llm_class):
        runtime = self.build_runtime_in_temp_workspace()

        self.assertIsInstance(runtime, YCAgentRuntime)
        self.assertIsInstance(runtime.agent, SkillRuntimeAgent)

    @patch("main.YCAgentsLLM", return_value=FakeLLM())
    def test_build_runtime_registers_markdown_writer_tool(self, _mock_llm_class):
        runtime = self.build_runtime_in_temp_workspace()

        self.assertTrue(runtime.expects_json)
        self.assertIn("markdown_writer", runtime.allowed_tools)
        self.assertIsInstance(
            runtime.tool_registry.get_tool("markdown_writer"),
            MarkdownWriterTool,
        )

    @patch("main.YCAgentsLLM", return_value=FakeLLM())
    def test_build_runtime_registers_reader_and_rag_tools(self, _mock_llm_class):
        runtime = self.build_runtime_in_temp_workspace()

        self.assertIn("docx_reader", runtime.allowed_tools)
        self.assertIn("rag_search", runtime.allowed_tools)
        self.assertIsInstance(
            runtime.tool_registry.get_tool("docx_reader"),
            DocxReaderTool,
        )
        self.assertIsInstance(
            runtime.tool_registry.get_tool("rag_search"),
            RAGSearchTool,
        )

    @patch("main.YCAgentsLLM", return_value=FakeLLM())
    def test_build_runtime_configures_session_memory(self, _mock_llm_class):
        runtime = self.build_runtime_in_temp_workspace()

        self.assertIsInstance(runtime.agent.session_memory, SessionMemory)

    @patch("main.YCAgentsLLM", return_value=FakeLLM())
    def test_build_runtime_configures_enhanced_memory_and_rag(self, _mock_llm_class):
        runtime = self.build_runtime_in_temp_workspace()

        self.assertIsInstance(runtime.agent.summary_memory, SummaryMemory)
        self.assertIsInstance(runtime.agent.profile_memory, ResearchProfileMemory)
        self.assertIsInstance(runtime.agent.memory_compressor, MemoryCompressor)
        self.assertIsInstance(runtime.agent.rag_search_tool, RAGSearchTool)
        self.assertGreater(runtime.agent.compression_threshold, 0)

    @patch("main.YCAgentsLLM", return_value=FakeLLM())
    def test_build_runtime_configures_permission_gate(self, _mock_llm_class):
        runtime = self.build_runtime_in_temp_workspace()

        self.assertIsInstance(runtime.approval_gate, HumanApprovalGate)

    def test_main_exports_build_runtime(self):
        self.assertTrue(callable(main.build_runtime))

    @patch("main.run_tui")
    @patch("main.build_cli_runtime")
    @patch("main.YCAgentsLLM", return_value=FakeLLM())
    @patch("main.load_dotenv")
    def test_main_loads_env_builds_runtime_and_starts_tui(
        self,
        mock_load_dotenv,
        _mock_llm_class,
        mock_build_cli_runtime,
        mock_run_tui,
    ):
        runtime = object()
        mock_build_cli_runtime.return_value = runtime
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)

        with patch(
            "main.WorkspaceStore",
            side_effect=lambda: WorkspaceStore(ycore_root=root, startup_dir=root),
        ):
            main.main()

        mock_load_dotenv.assert_called_once_with()
        mock_build_cli_runtime.assert_called_once()
        args, kwargs = mock_run_tui.call_args
        self.assertEqual(args, (runtime,))
        self.assertIn("workspace_store", kwargs)
        self.assertIn("workspace", kwargs)
        self.assertIn("session_store", kwargs)
        self.assertIn("session", kwargs)
        self.assertIn("runtime_builder", kwargs)

    def test_main_imports_tui_entrypoint(self):
        self.assertTrue(callable(main.run_tui))

    def test_build_mcp_tools_uses_config_when_client_is_supplied(self):
        class FakeClient:
            def call_tool(self, server_name, tool_name, arguments):
                return {"server_name": server_name, "tool_name": tool_name}

        tools = main.build_mcp_tools(client=FakeClient())

        self.assertGreaterEqual(len(tools), 1)
        self.assertIsInstance(tools[0], MCPToolAdapter)


if __name__ == "__main__":
    unittest.main()
