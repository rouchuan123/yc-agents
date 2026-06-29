import json
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from yc_agents.cli.runtime_factory import build_cli_runtime
from yc_agents.cli.sessions import CLISessionStore
from yc_agents.cli.workspaces import WorkspaceStore


class FakeLLM:
    model = "fake-model"

    def think(self, messages, **kwargs):
        return "ok"


class ConfiguredFakeLLM(FakeLLM):
    pass


def write_ycore_config(root, allow_tools=None, analytics_enabled=False, sqlite_mcp_enabled=False):
    default_allow_tools = [
        "workspace_files",
        "file_reader",
        "markdown_writer",
        "rag_search",
        "web_search",
        "git_inspector",
        "code_search",
        "verification_runner",
        "command_reader",
    ]
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
                            "request": {"max_tokens": 4096, "temperature": 0.2},
                        }
                    ],
                }
            }
        },
        "tools": {
            "allow": allow_tools or default_allow_tools,
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
            "maxToolCalls": 7,
            "toolTimeoutSeconds": 11,
            "invalidJsonRetryCount": 1,
            "failOnInvalidJson": True,
        },
        "analytics": {
            "enabled": analytics_enabled,
            "sqliteMcp": {"enabled": sqlite_mcp_enabled},
        },
        "memory": {"compressionThreshold": 5},
    }
    (root / "ycore.json").write_text(json.dumps(config), encoding="utf-8")
    (root / ".ycore").mkdir(exist_ok=True)
    (root / ".ycore" / "ycore.json").write_text(json.dumps(config), encoding="utf-8")


class TestCLIRuntimeFactory(unittest.TestCase):
    def setUp(self):
        self.global_config_dir = tempfile.TemporaryDirectory()
        self.global_config_root = Path(self.global_config_dir.name)
        write_ycore_config(self.global_config_root)
        self.global_config_patch = unittest.mock.patch(
            "yc_agents.config.ycore.YCoreConfig.default_global_config_path",
            return_value=self.global_config_root / "ycore.json",
        )
        self.global_config_patch.start()
        self.env_patch = unittest.mock.patch.dict(
            os.environ,
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

    def test_build_cli_runtime_uses_global_ycore_when_workspace_has_no_ycore(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            global_root = root / "global"
            workspace_root = root / "workspace"
            global_root.mkdir()
            workspace_root.mkdir()
            write_ycore_config(
                global_root,
                allow_tools=["workspace_files"],
                analytics_enabled=True,
                sqlite_mcp_enabled=True,
            )
            workspace = WorkspaceStore(
                ycore_root=root / "state",
                startup_dir=workspace_root,
            ).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("analytics")

            with unittest.mock.patch(
                "yc_agents.config.ycore.YCoreConfig.default_global_config_path",
                return_value=global_root / "ycore.json",
            ):
                runtime = build_cli_runtime(
                    session,
                    llm=FakeLLM(),
                    skills_dir=global_root / "skills",
                )

            try:
                self.assertIsNotNone(runtime.analytics_recorder)
                self.assertEqual(
                    runtime.analytics_recorder.config.db_path,
                    workspace.path / ".ycore" / "sqlite" / "analytics.sqlite",
                )
                self.assertIn("workspace_files", runtime.allowed_tools)
                self.assertIn("mcp_sqlite_query_readonly", runtime.allowed_tools)
            finally:
                runtime.close()

    def test_build_cli_runtime_applies_workspace_dot_ycore_override_to_global_ycore(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            global_root = root / "global"
            workspace_root = root / "workspace"
            global_root.mkdir()
            workspace_root.mkdir()
            (workspace_root / ".ycore").mkdir()
            write_ycore_config(
                global_root,
                allow_tools=["workspace_files"],
                analytics_enabled=False,
                sqlite_mcp_enabled=False,
            )
            (workspace_root / ".ycore" / "ycore.json").write_text(
                json.dumps(
                    {
                        "analytics": {
                            "enabled": True,
                            "sqliteMcp": {"enabled": True},
                        }
                    }
                ),
                encoding="utf-8",
            )
            workspace = WorkspaceStore(
                ycore_root=root / "state",
                startup_dir=workspace_root,
            ).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("analytics")

            with unittest.mock.patch(
                "yc_agents.config.ycore.YCoreConfig.default_global_config_path",
                return_value=global_root / "ycore.json",
            ):
                runtime = build_cli_runtime(
                    session,
                    llm=FakeLLM(),
                    skills_dir=global_root / "skills",
                )

            try:
                self.assertIsNotNone(runtime.analytics_recorder)
                self.assertIn("mcp_sqlite_query_readonly", runtime.allowed_tools)
                self.assertEqual(runtime.allowed_tools[0], "workspace_files")
            finally:
                runtime.close()

    def test_runtime_factory_uses_session_specific_memory_paths(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("代码审查")

            runtime = build_cli_runtime(session, llm=FakeLLM(), skills_dir=root / "skills")

            agent = runtime.agent
            self.assertEqual(agent.session_memory.file_path, session.messages_path)
            self.assertEqual(agent.summary_memory.file_path, session.summary_path)
            self.assertEqual(agent.profile_memory.file_path, session.profile_path)
            self.assertEqual(runtime.output_root, session.runs_path)

    def test_runtime_factory_registers_workspace_file_tools(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("代码体检")

            runtime = build_cli_runtime(session, llm=FakeLLM(), skills_dir=root / "skills")

            self.assertIn("workspace_files", runtime.allowed_tools)
            self.assertIn("file_reader", runtime.allowed_tools)
            self.assertEqual(
                runtime.tool_registry.get_tool("workspace_files").workspace_root,
                workspace.path,
            )
            self.assertEqual(
                runtime.tool_registry.get_tool("file_reader").workspace_root,
                workspace.path,
            )

    def test_runtime_factory_loads_ycore_instruction_layers(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            (workspace.path / "YCORE.md").write_text(
                "Root project instruction",
                encoding="utf-8",
            )
            (workspace.path / ".ycore").mkdir(exist_ok=True)
            (workspace.path / ".ycore" / "YCORE.md").write_text(
                "Local workspace instruction",
                encoding="utf-8",
            )
            session = CLISessionStore(workspace).create_session("generic")

            runtime = build_cli_runtime(session, llm=FakeLLM(), skills_dir=root / "skills")

            instructions = runtime.agent.prompt_builder.project_instructions
            self.assertEqual(
                [instruction.source for instruction in instructions],
                ["YCORE.md", ".ycore/YCORE.md"],
            )
            self.assertEqual(instructions[0].content, "Root project instruction")
            self.assertEqual(instructions[1].content, "Local workspace instruction")

    def test_runtime_factory_does_not_expose_word_formatting_as_default_tool(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("generic")

            runtime = build_cli_runtime(session, llm=FakeLLM(), skills_dir=root / "skills")

            removed_tool = "docx" + "_format" + "_normalizer"

            self.assertNotIn(removed_tool, runtime.allowed_tools)
            self.assertNotIn(
                removed_tool,
                runtime.agent.workspace_context["available_tools"],
            )

    def test_runtime_factory_registers_generic_web_search_tool(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("web")

            runtime = build_cli_runtime(session, llm=FakeLLM(), skills_dir=root / "skills")

            self.assertIn("web_search", runtime.allowed_tools)
            self.assertEqual(runtime.tool_registry.get_tool("web_search").name, "web_search")
            self.assertIn("web_search", runtime.agent.workspace_context["available_tools"])

    def test_runtime_factory_registers_review_evidence_tools(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("review")

            runtime = build_cli_runtime(session, llm=FakeLLM(), skills_dir=root / "skills")

            for tool_name in ["git_inspector", "code_search", "verification_runner"]:
                with self.subTest(tool_name=tool_name):
                    self.assertIn(tool_name, runtime.allowed_tools)
                    self.assertEqual(runtime.tool_registry.get_tool(tool_name).name, tool_name)
                    self.assertIn(tool_name, runtime.agent.workspace_context["available_tools"])

    def test_runtime_factory_registers_command_reader_as_global_but_skill_gated_tool(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("review")

            runtime = build_cli_runtime(session, llm=FakeLLM(), skills_dir=root / "skills")

            self.assertIn("command_reader", runtime.allowed_tools)
            self.assertEqual(runtime.tool_registry.get_tool("command_reader").name, "command_reader")
            self.assertIn("command_reader", runtime.agent.workspace_context["available_tools"])

    def test_build_cli_runtime_uses_ycore_tool_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            write_ycore_config(root, allow_tools=["workspace_files", "file_reader"])
            session = CLISessionStore(workspace).create_session("configured")

            with unittest.mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
                runtime = build_cli_runtime(
                    session,
                    llm=ConfiguredFakeLLM(),
                    skills_dir=root / "skills",
                )

            self.assertEqual(runtime.allowed_tools, ["workspace_files", "file_reader"])
            self.assertEqual(
                runtime.agent.workspace_context["available_tools"],
                ["workspace_files", "file_reader"],
            )
            self.assertEqual(runtime.agent.compression_threshold, 5)
            self.assertEqual(runtime.context_limit, 64000)

    def test_build_cli_runtime_passes_ycore_tavily_key_to_web_search(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            write_ycore_config(root, allow_tools=["web_search"])
            session = CLISessionStore(workspace).create_session("configured")

            with unittest.mock.patch.dict(os.environ, {"TAVILY_API_KEY": "configured-tavily"}, clear=False):
                runtime = build_cli_runtime(
                    session,
                    llm=ConfiguredFakeLLM(),
                    skills_dir=root / "skills",
                )

            web_tool = runtime.tool_registry.get_tool("web_search")
            self.assertEqual(web_tool.provider.api_key, "configured-tavily")

    def test_build_cli_runtime_applies_invalid_json_policy_from_ycore(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            write_ycore_config(root, allow_tools=["workspace_files"])
            session = CLISessionStore(workspace).create_session("configured")

            runtime = build_cli_runtime(
                session,
                llm=ConfiguredFakeLLM(),
                skills_dir=root / "skills",
            )

            self.assertEqual(runtime.invalid_json_retry_count, 1)
            self.assertTrue(runtime.fail_on_invalid_json)

    def test_build_cli_runtime_attaches_intent_router(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("intent")

            runtime = build_cli_runtime(session, llm=FakeLLM(), skills_dir=root / "skills")

            self.assertIsNotNone(runtime.agent.intent_router)

    def test_env_example_contains_only_secret_placeholders(self):
        env_example = Path(".env.example").read_text(encoding="utf-8")

        self.assertIn("DEEPSEEK_API_KEY=", env_example)
        self.assertIn("TAVILY_API_KEY=", env_example)

        for forbidden in [
            "LLM_PROVIDER",
            "LLM_MODEL_ID",
            "LLM_API_KEY",
            "LLM_BASE_URL",
            "LLM_TIMEOUT",
            "YCORE_ANALYTICS_",
            "YCORE_SQLITE_MCP_ENABLED",
        ]:
            self.assertNotIn(forbidden, env_example)

    def test_root_ycore_json_uses_env_secret_references_and_excludes_workspace_state(self):
        data = json.loads(Path("ycore.json").read_text(encoding="utf-8"))
        provider = data["models"]["providers"]["deepseek"]
        search = data["tools"]["web"]["search"]
        model = provider["models"][0]

        self.assertNotIn("workspaces", data)
        self.assertNotIn("apiKey", provider)
        self.assertEqual(provider["apiKeyEnv"], "DEEPSEEK_API_KEY")
        self.assertEqual(model["contextWindow"], 64000)
        self.assertEqual(model["maxOutputTokens"], 4096)
        self.assertEqual(model["request"]["max_tokens"], 4096)
        self.assertEqual(model["request"]["temperature"], 0.2)
        self.assertEqual(model["request"]["top_p"], 0.95)
        self.assertEqual(data["runtime"]["modelTimeoutSeconds"], 60)
        self.assertIn("analytics", data)
        self.assertNotIn("apiKey", search)
        self.assertEqual(search["apiKeyEnv"], "TAVILY_API_KEY")

    def test_build_cli_runtime_registers_sqlite_mcp_tools_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_ycore_config(
                root,
                allow_tools=["workspace_files"],
                analytics_enabled=False,
                sqlite_mcp_enabled=True,
            )
            workspace = WorkspaceStore(
                ycore_root=root,
                startup_dir=root,
            ).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("analytics")

            runtime = build_cli_runtime(
                session,
                llm=FakeLLM(),
                skills_dir=root / "skills",
            )

            try:
                tool_names = set(runtime.tool_registry.tools)
                self.assertIn("mcp_sqlite_list_tables", tool_names)
                self.assertIn("mcp_sqlite_describe_table", tool_names)
                self.assertIn("mcp_sqlite_query_readonly", tool_names)
                self.assertIn("mcp_sqlite_query_readonly", runtime.allowed_tools)
                self.assertIn(
                    "mcp_sqlite_query_readonly",
                    runtime.agent.workspace_context["available_tools"],
                )
            finally:
                runtime.close()

    def test_build_cli_runtime_configures_analytics_recorder_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_ycore_config(
                root,
                allow_tools=["workspace_files"],
                analytics_enabled=True,
                sqlite_mcp_enabled=False,
            )
            workspace = WorkspaceStore(
                ycore_root=root,
                startup_dir=root,
            ).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("analytics")

            runtime = build_cli_runtime(
                session,
                llm=FakeLLM(),
                skills_dir=root / "skills",
            )

            self.assertIsNotNone(runtime.analytics_recorder)
            self.assertEqual(
                runtime.analytics_recorder.config.db_path,
                workspace.path / ".ycore" / "sqlite" / "analytics.sqlite",
            )


if __name__ == "__main__":
    unittest.main()
