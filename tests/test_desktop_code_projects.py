import tempfile
import unittest
from pathlib import Path

from yc_agents.desktop.code_projects import CodeProjectService


class TestCodeProjectService(unittest.TestCase):
    def test_bind_project_persists_read_only_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            thesis = Path(tmp) / "thesis"
            code = Path(tmp) / "code"
            code.mkdir(parents=True)

            service = CodeProjectService(thesis)
            binding = service.bind("Demo Code", code)

            self.assertEqual(binding["name"], "Demo Code")
            self.assertEqual(binding["mode"], "read_only")
            self.assertEqual(service.list_projects()[0]["path"], str(code.resolve()))

    def test_tree_lists_files_and_skips_hidden_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            thesis = Path(tmp) / "thesis"
            code = Path(tmp) / "code"
            (code / ".git").mkdir(parents=True)
            (code / ".git" / "config").write_text("secret", encoding="utf-8")
            (code / "src").mkdir()
            (code / "src" / "app.py").write_text("print('hi')", encoding="utf-8")

            service = CodeProjectService(thesis)
            binding = service.bind("Demo Code", code)
            tree = service.tree(binding["id"])

            paths = [item["relative_path"] for item in tree]
            self.assertEqual(paths, ["src/app.py"])

    def test_select_files_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            thesis = Path(tmp) / "thesis"
            code = Path(tmp) / "code"
            code.mkdir(parents=True)

            service = CodeProjectService(thesis)
            binding = service.bind("Demo Code", code)

            with self.assertRaises(ValueError):
                service.select_files(binding["id"], ["../outside.py"])

    def test_select_files_persists_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            thesis = Path(tmp) / "thesis"
            code = Path(tmp) / "code"
            (code / "src").mkdir(parents=True)
            (code / "src" / "app.py").write_text("print('hi')", encoding="utf-8")

            service = CodeProjectService(thesis)
            binding = service.bind("Demo Code", code)
            selected = service.select_files(binding["id"], ["src/app.py"])

            self.assertEqual(selected["selected_files"], ["src/app.py"])
            self.assertEqual(service.list_projects()[0]["selected_files"], ["src/app.py"])


if __name__ == "__main__":
    unittest.main()
