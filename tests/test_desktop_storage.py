import json
import tempfile
import unittest
from pathlib import Path

from yc_agents.desktop.storage import ProjectStore


class TestProjectStore(unittest.TestCase):
    def test_create_project_writes_expected_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "my-thesis"
            store = ProjectStore()

            project = store.create_project(root, "My Thesis")

            self.assertEqual(project["name"], "My Thesis")
            self.assertTrue((root / "project.json").exists())
            self.assertTrue((root / "documents" / "literature").is_dir())
            self.assertTrue((root / "documents" / "notes").is_dir())
            self.assertTrue((root / "documents" / "requirements").is_dir())
            self.assertTrue((root / "documents" / "thesis").is_dir())
            self.assertTrue((root / "code_projects").is_dir())
            self.assertTrue((root / "sessions").is_dir())
            self.assertTrue((root / "runs").is_dir())
            self.assertTrue((root / "memory").is_dir())
            self.assertTrue((root / "exports").is_dir())

    def test_open_project_reads_project_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "my-thesis"
            store = ProjectStore()
            created = store.create_project(root, "My Thesis")

            opened = store.open_project(root)

            self.assertEqual(opened["id"], created["id"])
            self.assertEqual(opened["root"], str(root.resolve()))

    def test_open_project_rejects_missing_project_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore()

            with self.assertRaises(FileNotFoundError):
                store.open_project(Path(tmp) / "missing")

    def test_project_json_contains_relative_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "my-thesis"
            store = ProjectStore()
            store.create_project(root, "My Thesis")

            data = json.loads((root / "project.json").read_text(encoding="utf-8"))

            self.assertEqual(data["documents_dir"], "documents")
            self.assertEqual(data["runs_dir"], "runs")
            self.assertEqual(data["memory_dir"], "memory")


if __name__ == "__main__":
    unittest.main()
