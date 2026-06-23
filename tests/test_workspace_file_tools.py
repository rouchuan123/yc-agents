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
            (workspace / "paper.pdf").write_bytes(b"%PDF fake")
            (workspace / "notes.docx").write_bytes(b"fake")
            (workspace / "draft.md").write_text("# Draft", encoding="utf-8")
            (workspace / "ignore.tmp").write_text("x", encoding="utf-8")

            result = WorkspaceFilesTool(workspace).run()

            names = [item["path"] for item in result["files"]]
            self.assertEqual(names, ["draft.md", "notes.docx", "paper.pdf"])
            self.assertEqual(result["workspace"], str(workspace.resolve()))
            self.assertEqual(result["count"], 3)


class TestFileReaderTool(unittest.TestCase):
    def test_reads_docx_relative_to_workspace(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            path = workspace / "paper.docx"
            document = Document()
            document.add_paragraph("研究背景")
            document.save(path)

            result = FileReaderTool(workspace).run("paper.docx")

            self.assertEqual(result["path"], "paper.docx")
            self.assertEqual(result["file_type"], "docx")
            self.assertIn("研究背景", result["text"])

    def test_reads_pdf_relative_to_workspace(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            path = workspace / "paper.pdf"
            path.write_bytes(b"%PDF fake")

            class FakePage:
                def extract_text(self):
                    return "PDF 正文"

            class FakeReader:
                def __init__(self, _path):
                    self.pages = [FakePage()]

            tool = FileReaderTool(workspace, pdf_reader_class=FakeReader)

            result = tool.run("paper.pdf")

            self.assertEqual(result["path"], "paper.pdf")
            self.assertEqual(result["file_type"], "pdf")
            self.assertIn("PDF 正文", result["text"])

    def test_rejects_paths_outside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)

            with self.assertRaises(PermissionError):
                FileReaderTool(workspace).run("../outside.pdf")


if __name__ == "__main__":
    unittest.main()
