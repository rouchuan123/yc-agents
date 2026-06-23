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
            session = CLISessionStore(workspace).create_session("开题报告")

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
            session = CLISessionStore(workspace).create_session("文献")

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


if __name__ == "__main__":
    unittest.main()
