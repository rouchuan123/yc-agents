import tempfile
import unittest
from pathlib import Path

from yc_agents.cli.runtime_factory import build_cli_runtime
from yc_agents.cli.sessions import CLISessionStore
from yc_agents.cli.workspaces import WorkspaceStore


class FakeLLM:
    model = "fake-model"

    def think(self, messages, **kwargs):
        return "ok"


class TestCLIRuntimeFactory(unittest.TestCase):
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

    def test_build_cli_runtime_attaches_intent_router(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            session = CLISessionStore(workspace).create_session("intent")

            runtime = build_cli_runtime(session, llm=FakeLLM(), skills_dir=root / "skills")

            self.assertIsNotNone(runtime.agent.intent_router)

    def test_env_example_documents_tavily_api_key(self):
        env_example = Path(".env.example").read_text(encoding="utf-8")

        self.assertIn("TAVILY_API_KEY=", env_example)


if __name__ == "__main__":
    unittest.main()
