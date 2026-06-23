import json
import tempfile
import unittest
from pathlib import Path

from yc_agents.cli.sessions import CLISessionStore
from yc_agents.cli.workspaces import WorkspaceStore


class TestCLISessionStore(unittest.TestCase):
    def _workspace(self, root, name):
        path = root / name
        path.mkdir()
        return WorkspaceStore(ycore_root=root, startup_dir=path).add_workspace(path)

    def test_ensure_current_session_creates_default_session(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)

            session = store.ensure_current_session()

            self.assertEqual(session.title, "新会话 1")
            self.assertTrue(session.messages_path.exists())
            self.assertEqual(context.current_session_path.read_text(encoding="utf-8"), session.id)

    def test_session_new_with_title_switches_current(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)

            session = store.create_session("开题报告")

            self.assertEqual(session.title, "开题报告")
            self.assertEqual(store.ensure_current_session().id, session.id)
            metadata = json.loads((session.path / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["title"], "开题报告")

    def test_sessions_are_isolated_by_workspace(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            first_context = self._workspace(root, "first")
            second_context = self._workspace(root, "second")
            first = CLISessionStore(first_context)
            second = CLISessionStore(second_context)

            first_session = first.create_session("开题报告")
            second_session = second.create_session("文献综述")

            first_session.messages_path.write_text(
                json.dumps([{"role": "user", "content": "A"}]),
                encoding="utf-8",
            )
            second_session.messages_path.write_text(
                json.dumps([{"role": "user", "content": "B"}]),
                encoding="utf-8",
            )

            self.assertNotEqual(first_session.path, second_session.path)
            self.assertEqual(first.load_transcript(), [("You", "A")])
            self.assertEqual(second.load_transcript(), [("You", "B")])

    def test_switch_session_reloads_current_session(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)
            first = store.create_session("A")
            second = store.create_session("B")

            switched = store.switch_session(first.id)

            self.assertEqual(switched.id, first.id)
            self.assertEqual(store.ensure_current_session().id, first.id)
            self.assertEqual(store.switch_session(second.id).id, second.id)

    def test_delete_session_removes_session_and_runs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)
            first = store.create_session("A")
            second = store.create_session("B")
            run_dir = first.runs_path / "run_001"
            run_dir.mkdir(parents=True)

            next_session = store.delete_session(first.id)

            self.assertEqual(next_session.id, second.id)
            self.assertFalse(first.path.exists())
            self.assertFalse(first.runs_path.exists())

    def test_delete_only_session_creates_replacement(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)
            first = store.create_session("Only")

            replacement = store.delete_session(first.id)

            self.assertNotEqual(replacement.id, first.id)
            self.assertEqual(replacement.title, "新会话 1")
            self.assertTrue(replacement.path.exists())
            self.assertEqual(store.ensure_current_session().id, replacement.id)

    def test_load_transcript_limits_recent_messages(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = WorkspaceStore(ycore_root=root, startup_dir=root).ensure_active_workspace()
            store = CLISessionStore(context)
            session = store.create_session("History")
            messages = [
                {"role": "user", "content": "old"},
                {"role": "assistant", "content": "older"},
                {"role": "user", "content": "new"},
                {"role": "assistant", "content": "newer"},
            ]
            session.messages_path.write_text(json.dumps(messages), encoding="utf-8")

            self.assertEqual(
                store.load_transcript(limit=2),
                [("You", "new"), ("Assistant", "newer")],
            )


if __name__ == "__main__":
    unittest.main()
