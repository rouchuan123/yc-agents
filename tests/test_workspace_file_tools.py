import tempfile
import unittest
from pathlib import Path

from docx import Document

from yc_agents.tools.file_reader import FileReaderTool
from yc_agents.tools.workspace_files import WorkspaceFilesTool


class TestWorkspaceFilesTool(unittest.TestCase):
    def test_lists_supported_workspace_files_without_ycore(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / ".ycore").mkdir()
            (workspace / ".ycore" / "workspace.json").write_text("{}", encoding="utf-8")
            (workspace / "spec.pdf").write_bytes(b"%PDF fake")
            (workspace / "notes.docx").write_bytes(b"fake")
            (workspace / "draft.md").write_text("# Draft", encoding="utf-8")
            (workspace / "ignore.tmp").write_text("x", encoding="utf-8")

            result = WorkspaceFilesTool(workspace).run()

            names = [item["path"] for item in result["files"]]
            self.assertEqual(names, ["draft.md", "notes.docx", "spec.pdf"])
            self.assertEqual(result["workspace"], str(workspace.resolve()))
            self.assertEqual(result["count"], 3)

    def test_lists_code_and_config_files_without_secret_env_or_heavy_dirs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / "src").mkdir()
            (workspace / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
            (workspace / "pom.xml").write_text("<project />", encoding="utf-8")
            (workspace / "Dockerfile").write_text("FROM python:3.12", encoding="utf-8")
            (workspace / ".env").write_text("SECRET=1", encoding="utf-8")
            (workspace / ".env.example").write_text("SECRET=", encoding="utf-8")
            (workspace / "node_modules").mkdir()
            (workspace / "node_modules" / "lib.js").write_text("x", encoding="utf-8")
            (workspace / ".git").mkdir()
            (workspace / ".git" / "config").write_text("x", encoding="utf-8")

            result = WorkspaceFilesTool(workspace).run()

            paths = [item["path"].replace("\\", "/") for item in result["files"]]
            self.assertIn("src/app.py", paths)
            self.assertIn("pom.xml", paths)
            self.assertIn("Dockerfile", paths)
            self.assertIn(".env.example", paths)
            self.assertNotIn(".env", paths)
            self.assertNotIn("node_modules/lib.js", paths)
            self.assertNotIn(".git/config", paths)

    def test_custom_excluded_dirs_are_added_to_default_excludes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / "generated").mkdir()
            (workspace / "generated" / "client.ts").write_text("export {}", encoding="utf-8")
            (workspace / ".ycore").mkdir()
            (workspace / ".ycore" / "memory.md").write_text("private", encoding="utf-8")
            (workspace / "src").mkdir()
            (workspace / "src" / "main.ts").write_text("export {}", encoding="utf-8")

            result = WorkspaceFilesTool(workspace, excluded_dirs={"generated"}).run()

            paths = [item["path"].replace("\\", "/") for item in result["files"]]
            self.assertEqual(paths, ["src/main.ts"])


class TestFileReaderTool(unittest.TestCase):
    def test_reads_docx_relative_to_workspace(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            path = workspace / "requirements.docx"
            document = Document()
            document.add_paragraph("接口说明")
            document.save(path)

            result = FileReaderTool(workspace).run("requirements.docx")

            self.assertEqual(result["path"], "requirements.docx")
            self.assertEqual(result["file_type"], "docx")
            self.assertIn("接口说明", result["text"])

    def test_reads_pdf_relative_to_workspace(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            path = workspace / "spec.pdf"
            path.write_bytes(b"%PDF fake")

            class FakePage:
                def extract_text(self):
                    return "PDF 正文"

            class FakeReader:
                def __init__(self, _path):
                    self.pages = [FakePage()]

            tool = FileReaderTool(workspace, pdf_reader_class=FakeReader)

            result = tool.run("spec.pdf")

            self.assertEqual(result["path"], "spec.pdf")
            self.assertEqual(result["file_type"], "pdf")
            self.assertIn("PDF 正文", result["text"])

    def test_rejects_paths_outside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)

            with self.assertRaises(PermissionError):
                FileReaderTool(workspace).run("../outside.pdf")

    def test_reads_python_and_special_text_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / "app.py").write_text("def handler():\n    return 'ok'\n", encoding="utf-8")
            (workspace / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")

            py_result = FileReaderTool(workspace).run("app.py")
            docker_result = FileReaderTool(workspace).run("Dockerfile")

            self.assertTrue(py_result["ok"])
            self.assertEqual(py_result["file_type"], "py")
            self.assertIn("def handler", py_result["text"])
            self.assertTrue(docker_result["ok"])
            self.assertEqual(docker_result["file_type"], "Dockerfile")
            self.assertIn("FROM python", docker_result["text"])

    def test_rejects_secret_env_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / ".env").write_text("SECRET=1", encoding="utf-8")

            with self.assertRaises(PermissionError):
                FileReaderTool(workspace).run(".env")

    def test_reads_env_example_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / ".env.example").write_text("SECRET=", encoding="utf-8")

            result = FileReaderTool(workspace).run(".env.example")

            self.assertTrue(result["ok"])
            self.assertEqual(result["file_type"], "env.example")
            self.assertIn("SECRET=", result["text"])

    def test_large_text_file_returns_structured_refusal_without_allow_large(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / "large.py").write_text("x" * (201 * 1024), encoding="utf-8")

            result = FileReaderTool(workspace).run("large.py")

            self.assertFalse(result["ok"])
            self.assertEqual(result["error_type"], "file_too_large")
            self.assertEqual(result["limit_bytes"], 200 * 1024)
            self.assertIn("code_search", result["recommendation"])

    def test_large_text_file_reads_with_allow_large_until_hard_cap(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / "large.py").write_text("x" * (201 * 1024), encoding="utf-8")

            result = FileReaderTool(workspace).run("large.py", allow_large=True)

            self.assertTrue(result["ok"])
            self.assertFalse(result["truncated"])
            self.assertEqual(result["characters"], 201 * 1024)

    def test_text_file_over_hard_cap_returns_structured_refusal(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / "huge.py").write_text("x" * (2 * 1024 * 1024 + 1), encoding="utf-8")

            result = FileReaderTool(workspace).run("huge.py", allow_large=True)

            self.assertFalse(result["ok"])
            self.assertEqual(result["error_type"], "file_too_large")
            self.assertEqual(result["limit_bytes"], 2 * 1024 * 1024)

    def test_large_pdf_returns_preview_without_allow_large(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            path = workspace / "large.pdf"
            path.write_bytes(b"%PDF fake")

            class FakePage:
                def extract_text(self):
                    return "a" * 40000

            class FakeReader:
                def __init__(self, _path):
                    self.pages = [FakePage()]

            result = FileReaderTool(workspace, pdf_reader_class=FakeReader).run("large.pdf")

            self.assertTrue(result["ok"])
            self.assertTrue(result["truncated"])
            self.assertEqual(result["characters"], 30000)
            self.assertEqual(result["original_characters"], 40000)


if __name__ == "__main__":
    unittest.main()
