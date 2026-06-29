import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.cli.workspaces import WorkspaceStore
from yc_agents.harness.permissions import HumanApprovalGate
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.compressor import MemoryCompressor
from yc_agents.memory.profile import CodeAgentProfileMemory
from yc_agents.memory.session import SessionMemory
from yc_agents.memory.summary import SummaryMemory
from yc_agents.tools.file_reader import FileReaderTool
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.mcp_adapter import MCPToolAdapter
from yc_agents.tools.rag_search import RAGSearchTool


class FakeLLM:
    pass


def write_ycore_config(root):
    config = {
        "agents": {
            "defaults": {
                "model": {
                    "primary": "deepseek/deepseek-v4-flash",
                    "fallbacks": [],
                },
            },
            "entries": {"main": {"enabled": True}},
        },
        "models": {
            "providers": {
                "deepseek": {
                    "baseUrl": "https://api.deepseek.com",
                    "api": "openai-completions",
                    "apiKeyEnv": "DEEPSEEK_API_KEY",
                    "models": [
                        {
                            "id": "deepseek-v4-flash",
                            "contextWindow": 64000,
                            "maxOutputTokens": 4096,
                            "request": {"max_tokens": 4096},
                        }
                    ],
                }
            }
        },
        "tools": {
            "allow": [
                "workspace_files",
                "file_reader",
                "markdown_writer",
                "rag_search",
                "web_search",
                "git_inspector",
                "code_search",
                "verification_runner",
                "command_reader",
            ],
            "web": {
                "search": {
                    "provider": "tavily",
                    "enabled": True,
                    "apiKeyEnv": "TAVILY_API_KEY",
                }
            },
        },
        "skills": {"dirs": ["skills"], "entries": {}},
        "runtime": {
            "expectsJson": True,
            "maxToolCalls": 12,
            "toolTimeoutSeconds": 30,
            "invalidJsonRetryCount": 1,
            "failOnInvalidJson": True,
        },
        "analytics": {
            "enabled": False,
            "sqliteMcp": {"enabled": False},
        },
        "memory": {"compressionThreshold": 12},
    }
    (root / "ycore.json").write_text(json.dumps(config), encoding="utf-8")


class TestMainEntryPoint(unittest.TestCase):
    def setUp(self):
        self.global_config_dir = tempfile.TemporaryDirectory()
        self.global_config_root = Path(self.global_config_dir.name)
        write_ycore_config(self.global_config_root)
        self.global_config_patch = patch(
            "yc_agents.config.ycore.YCoreConfig.default_global_config_path",
            return_value=self.global_config_root / "ycore.json",
        )
        self.global_config_patch.start()
        self.env_patch = patch.dict(
            "os.environ",
            {
                "DEEPSEEK_API_KEY": "test-deepseek",
                "TAVILY_API_KEY": "test-tavily",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.global_config_patch.stop()
        self.global_config_dir.cleanup()

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

        self.assertIn("file_reader", runtime.allowed_tools)
        self.assertIn("rag_search", runtime.allowed_tools)
        self.assertIsInstance(
            runtime.tool_registry.get_tool("file_reader"),
            FileReaderTool,
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
        self.assertIsInstance(runtime.agent.profile_memory, CodeAgentProfileMemory)
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

    def test_build_mcp_tools_uses_declared_tool_metadata(self):
        class StaticClient:
            def call_tool(self, server_name, tool_name, arguments):
                return {
                    "server": server_name,
                    "tool": tool_name,
                    "arguments": arguments,
                }

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "mcp_servers.json"
            path.write_text(
                json.dumps(
                    {
                        "servers": {
                            "filesystem": {
                                "description": "Filesystem MCP",
                                "tools": [
                                    {"name": "read_file", "description": "Read a file"},
                                    {
                                        "name": "list_directory",
                                        "description": "List directory",
                                    },
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            tools = main.build_mcp_tools(config_path=path, client=StaticClient())

        self.assertEqual(
            [tool.name for tool in tools],
            [
                "mcp_filesystem_read_file",
                "mcp_filesystem_list_directory",
            ],
        )
        self.assertEqual(tools[0].tool_name, "read_file")


if __name__ == "__main__":
    unittest.main()
