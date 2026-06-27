import json
import tempfile
import unittest
from pathlib import Path

from yc_agents.cli.workspaces import WorkspaceStore


class TestWorkspaceStore(unittest.TestCase):
    def test_first_start_initializes_current_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = WorkspaceStore(ycore_root=root, startup_dir=root)

            context = store.ensure_active_workspace()

            self.assertEqual(context.path, root.resolve())
            self.assertTrue((root / ".ycore" / "workspace.json").exists())
            self.assertEqual(store.load_index()["current_workspace_id"], context.id)

    def test_add_workspace_requires_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            missing = root / "missing"
            store = WorkspaceStore(ycore_root=root, startup_dir=root)

            with self.assertRaises(FileNotFoundError):
                store.add_workspace(missing)

            self.assertFalse((missing / ".ycore").exists())

    def test_add_workspace_creates_ycore_and_switches_current(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "code"
            workspace.mkdir()
            store = WorkspaceStore(ycore_root=root, startup_dir=root)
            initial = store.ensure_active_workspace()

            added = store.add_workspace(workspace)

            self.assertNotEqual(added.id, initial.id)
            self.assertEqual(added.path, workspace.resolve())
            self.assertTrue((workspace / ".ycore" / "workspace.json").exists())
            self.assertEqual(store.load_index()["current_workspace_id"], added.id)

    def test_switch_workspace_updates_current(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace = root / "code"
            workspace.mkdir()
            store = WorkspaceStore(ycore_root=root, startup_dir=root)
            first = store.ensure_active_workspace()
            second = store.add_workspace(workspace)

            switched = store.switch_workspace(first.id)

            self.assertEqual(switched.id, first.id)
            self.assertEqual(store.load_index()["current_workspace_id"], first.id)
            self.assertEqual(store.get_current_workspace().id, first.id)
            self.assertEqual(store.switch_workspace(second.id).id, second.id)

    def test_delete_current_workspace_falls_back_to_recent_remaining_workspace(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            other_path = root / "other"
            other_path.mkdir()
            store = WorkspaceStore(ycore_root=root, startup_dir=root)
            first = store.ensure_active_workspace()
            second = store.add_workspace(other_path)

            next_context = store.delete_workspace(second.id)

            self.assertEqual(next_context.id, first.id)
            self.assertFalse((other_path / ".ycore").exists())
            ids = [item["id"] for item in store.load_index()["workspaces"]]
            self.assertEqual(ids, [first.id])

    def test_delete_last_workspace_reinitializes_startup_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = WorkspaceStore(ycore_root=root, startup_dir=root)
            first = store.ensure_active_workspace()

            replacement = store.delete_workspace(first.id)

            self.assertNotEqual(replacement.id, first.id)
            self.assertEqual(replacement.path, root.resolve())
            self.assertTrue((root / ".ycore" / "workspace.json").exists())
            self.assertEqual(store.load_index()["current_workspace_id"], replacement.id)

    def test_workspace_json_contains_stable_identity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = WorkspaceStore(ycore_root=root, startup_dir=root)

            context = store.ensure_active_workspace()

            data = json.loads((root / ".ycore" / "workspace.json").read_text(encoding="utf-8"))
            self.assertEqual(data["id"], context.id)
            self.assertEqual(data["path"], str(root.resolve()))


if __name__ == "__main__":
    unittest.main()
