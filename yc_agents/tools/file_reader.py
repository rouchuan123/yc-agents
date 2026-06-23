from pathlib import Path

from docx import Document
from pypdf import PdfReader

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class FileReaderTool(BaseTool):
    name = "file_reader"
    description = "Read text from a workspace file. Supports .docx, .pdf, .md, and .txt."
    schema = ToolSchema(fields=[ToolField(name="file_path", type="str", required=True)])

    def __init__(self, workspace_root, pdf_reader_class=PdfReader):
        self.workspace_root = Path(workspace_root).resolve()
        self.pdf_reader_class = pdf_reader_class

    def run(self, file_path):
        path = self._resolve_workspace_path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".docx":
            text = self._read_docx(path)
            file_type = "docx"
        elif suffix == ".pdf":
            text = self._read_pdf(path)
            file_type = "pdf"
        elif suffix in {".md", ".txt"}:
            text = path.read_text(encoding="utf-8")
            file_type = suffix.lstrip(".")
        else:
            raise ValueError(f"Unsupported readable file type: {path.suffix}")

        return {
            "path": str(path.relative_to(self.workspace_root)),
            "file_type": file_type,
            "text": text,
            "characters": len(text),
        }

    def _resolve_workspace_path(self, file_path):
        candidate = Path(str(file_path).strip())
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.workspace_root / candidate).resolve()

        if resolved != self.workspace_root and self.workspace_root not in resolved.parents:
            raise PermissionError(f"Path escapes active workspace: {file_path}")

        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"File not found in active workspace: {file_path}")

        return resolved

    def _read_docx(self, path):
        document = Document(path)
        return "\n".join(
            paragraph.text.strip()
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        )

    def _read_pdf(self, path):
        reader = self.pdf_reader_class(path)
        return "\n".join(
            text
            for page in reader.pages
            if (text := (page.extract_text() or "").strip())
        )
