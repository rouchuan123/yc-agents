import os
import tempfile
import unittest
from pathlib import Path

from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.workspace_write import WorkspaceWriteTool


class TestWorkspaceWriteTool(unittest.TestCase):
    def test_creates_nested_text_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tool = WorkspaceWriteTool(root)

            result = tool.run(
                file_path="docs/analysis.md",
                operation="create",
                content="# Analysis\n",
            )

            self.assertTrue(result["created"])
            self.assertEqual(result["path"], str(Path("docs/analysis.md")))
            self.assertEqual(
                (root / "docs" / "analysis.md").read_text(encoding="utf-8"),
                "# Analysis\n",
            )

    def test_write_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "app.py"
            path.write_text("old\n", encoding="utf-8")

            result = WorkspaceWriteTool(root).run(
                file_path="app.py",
                operation="write",
                content="new\n",
            )

            self.assertFalse(result["created"])
            self.assertEqual(path.read_text(encoding="utf-8"), "new\n")

    def test_replace_requires_exact_occurrence_count(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "app.py"
            path.write_text("value = 1\nvalue = 1\n", encoding="utf-8")
            tool = WorkspaceWriteTool(root)

            with self.assertRaisesRegex(ValueError, "expected 1 occurrence"):
                tool.run(
                    file_path="app.py",
                    operation="replace",
                    old_text="value = 1",
                    new_text="value = 2",
                )

            self.assertEqual(path.read_text(encoding="utf-8"), "value = 1\nvalue = 1\n")

    def test_replace_updates_requested_occurrences(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "app.py"
            path.write_text("value = 1\nvalue = 1\n", encoding="utf-8")

            result = WorkspaceWriteTool(root).run(
                file_path="app.py",
                operation="replace",
                old_text="value = 1",
                new_text="value = 2",
                expected_replacements=2,
            )

            self.assertEqual(result["replacements"], 2)
            self.assertEqual(path.read_text(encoding="utf-8"), "value = 2\nvalue = 2\n")

    def test_append_preserves_existing_content(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "notes.txt"
            path.write_text("first\n", encoding="utf-8")

            WorkspaceWriteTool(root).run(
                file_path="notes.txt",
                operation="append",
                content="second\n",
            )

            self.assertEqual(path.read_text(encoding="utf-8"), "first\nsecond\n")

    def test_create_refuses_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "README.md").write_text("existing", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "File already exists"):
                WorkspaceWriteTool(root).run(
                    file_path="README.md",
                    operation="create",
                    content="replacement",
                )

    def test_rejects_absolute_traversal_and_internal_paths(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = WorkspaceWriteTool(tmp_dir)
            paths = [
                str(Path(tmp_dir) / "outside.txt"),
                "../outside.txt",
                ".git/config",
                ".ycore/session.json",
            ]

            for file_path in paths:
                with self.subTest(file_path=file_path):
                    with self.assertRaises(PermissionError):
                        tool.run(file_path=file_path, content="blocked")

    def test_markdown_writer_rejects_internal_paths(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = MarkdownWriterTool(tmp_dir)

            with self.assertRaises(PermissionError):
                tool.run(file_name=".ycore/report.md", content="blocked")

    def test_rejects_symlink_that_escapes_workspace(self):
        with tempfile.TemporaryDirectory() as tmp_dir, tempfile.TemporaryDirectory() as outside_dir:
            root = Path(tmp_dir)
            link = root / "outside-link"
            try:
                os.symlink(outside_dir, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory symlinks are not available")

            with self.assertRaises(PermissionError):
                WorkspaceWriteTool(root).run(
                    file_path="outside-link/escaped.txt",
                    content="blocked",
                )


if __name__ == "__main__":
    unittest.main()
