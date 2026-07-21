import json
import os
import tempfile
import unittest
from pathlib import Path

from yc_agents.cli.workspaces import WorkspaceStore


class TestWorkspaceStore(unittest.TestCase):
    def test_default_store_keeps_registry_in_ycore_home_and_switches_startup_dirs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            home = root / "home"
            first_path = root / "first"
            second_path = root / "second"
            first_path.mkdir()
            second_path.mkdir()

            with unittest.mock.patch.dict(os.environ, {"YCORE_HOME": str(home)}):
                store = WorkspaceStore(startup_dir=first_path)
                first = store.add_workspace(first_path)
                second = store.add_workspace(second_path)
                repeated = store.add_workspace(second_path)

            self.assertEqual(store.index_path, home / "workspaces.json")
            self.assertEqual(first.path, first_path.resolve())
            self.assertEqual(second.path, second_path.resolve())
            self.assertEqual(repeated.id, second.id)
            self.assertEqual(len(store.load_index()["workspaces"]), 2)
            self.assertEqual(store.load_index()["current_workspace_id"], second.id)

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

    def test_workspace_store_keeps_workspace_state_out_of_root_ycore_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            workspace_path = root / "project"
            workspace_path.mkdir()
            store = WorkspaceStore(ycore_root=root, startup_dir=workspace_path)

            context = store.ensure_active_workspace()

            index_path = root / "data" / "workspaces.json"
            self.assertTrue(index_path.exists())
            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(index["current_workspace_id"], context.id)
            self.assertEqual(index["workspaces"][0]["path"], str(workspace_path.resolve()))

            workspace_json = workspace_path / ".ycore" / "workspace.json"
            self.assertTrue(workspace_json.exists())
            metadata = json.loads(workspace_json.read_text(encoding="utf-8"))
            self.assertEqual(metadata["id"], context.id)

            root_ycore = workspace_path / "ycore.json"
            if root_ycore.exists():
                data = json.loads(root_ycore.read_text(encoding="utf-8"))
                self.assertNotIn("workspaces", data)


if __name__ == "__main__":
    unittest.main()
