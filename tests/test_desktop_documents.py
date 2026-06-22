import tempfile
import unittest
from pathlib import Path

from yc_agents.desktop.documents import DocumentService


class TestDocumentService(unittest.TestCase):
    def test_scan_lists_supported_documents_under_documents_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "documents"
            (docs / "notes").mkdir(parents=True)
            (docs / "notes" / "idea.md").write_text("# Idea", encoding="utf-8")
            (docs / "notes" / "ignore.exe").write_text("no", encoding="utf-8")

            service = DocumentService(root)
            result = service.scan()

            paths = [item["relative_path"] for item in result]
            self.assertEqual(paths, ["documents/notes/idea.md"])

    def test_scan_lists_pdf_literature_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "documents" / "literature" / "paper.pdf"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"%PDF-1.4\n% test pdf placeholder\n")

            service = DocumentService(root)
            result = service.scan()

            self.assertEqual(result[0]["relative_path"], "documents/literature/paper.pdf")
            self.assertEqual(result[0]["extension"], ".pdf")

    def test_preview_reads_text_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "documents" / "notes" / "idea.md"
            path.parent.mkdir(parents=True)
            path.write_text("# Idea", encoding="utf-8")

            service = DocumentService(root)
            preview = service.preview("documents/notes/idea.md")

            self.assertEqual(preview["kind"], "text")
            self.assertEqual(preview["content"], "# Idea")

    def test_preview_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = DocumentService(Path(tmp))

            with self.assertRaises(ValueError):
                service.preview("../secret.md")

    def test_preview_reports_binary_docx_as_unsupported_text_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "documents" / "literature" / "paper.docx"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not-a-real-docx")

            service = DocumentService(root)
            preview = service.preview("documents/literature/paper.docx")

            self.assertEqual(preview["kind"], "binary")
            self.assertEqual(preview["content"], "")

    def test_preview_pdf_returns_structured_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "documents" / "literature" / "paper.pdf"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"%PDF-1.4\n% test pdf placeholder\n")

            service = DocumentService(root)
            preview = service.preview("documents/literature/paper.pdf")

            self.assertEqual(preview["relative_path"], "documents/literature/paper.pdf")
            self.assertIn(preview["kind"], ["text", "binary"])


if __name__ == "__main__":
    unittest.main()
