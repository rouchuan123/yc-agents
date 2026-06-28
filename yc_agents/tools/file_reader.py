from pathlib import Path

from docx import Document
from pypdf import PdfReader

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool
from yc_agents.tools.readable_files import (
    file_type_for_path,
    is_blocked_readable_file,
    is_readable_document_file,
    is_readable_text_file,
)


TEXT_DEFAULT_MAX_BYTES = 200 * 1024
TEXT_HARD_MAX_BYTES = 2 * 1024 * 1024
DOCUMENT_DEFAULT_MAX_CHARS = 30000
DOCUMENT_HARD_MAX_CHARS = 150000


class FileReaderTool(BaseTool):
    name = "file_reader"
    description = "Read text from a workspace file. Supports documents, code, and config files."
    schema = ToolSchema(
        fields=[
            ToolField(name="file_path", type="str", required=True),
            ToolField(name="allow_large", type="bool", required=False, default=False),
        ]
    )

    def __init__(self, workspace_root, pdf_reader_class=PdfReader):
        self.workspace_root = Path(workspace_root).resolve()
        self.pdf_reader_class = pdf_reader_class

    def run(self, file_path, allow_large=False):
        path = self._resolve_workspace_path(file_path)

        if is_blocked_readable_file(path):
            raise PermissionError(f"Refusing to read blocked file: {path.name}")

        if is_readable_text_file(path):
            return self._read_text_file(path, allow_large=allow_large)

        if is_readable_document_file(path):
            return self._read_document_file(path, allow_large=allow_large)

        raise ValueError(f"Unsupported readable file type: {path.suffix or path.name}")

    def _read_text_file(self, path, allow_large=False):
        size = path.stat().st_size
        limit = TEXT_HARD_MAX_BYTES if allow_large else TEXT_DEFAULT_MAX_BYTES
        if size > limit:
            return self._large_text_refusal(path, size, limit)

        text = path.read_text(encoding="utf-8", errors="replace")
        return {
            "ok": True,
            "path": str(path.relative_to(self.workspace_root)),
            "file_type": file_type_for_path(path),
            "text": text,
            "characters": len(text),
            "bytes": size,
            "truncated": False,
            "allow_large": bool(allow_large),
        }

    def _read_document_file(self, path, allow_large=False):
        suffix = path.suffix.lower()
        if suffix == ".docx":
            text = self._read_docx(path)
        elif suffix == ".pdf":
            text = self._read_pdf(path)
        else:
            raise ValueError(f"Unsupported readable document type: {path.suffix}")

        limit = DOCUMENT_HARD_MAX_CHARS if allow_large else DOCUMENT_DEFAULT_MAX_CHARS
        original_characters = len(text)
        preview = text[:limit]
        return {
            "ok": True,
            "path": str(path.relative_to(self.workspace_root)),
            "file_type": file_type_for_path(path),
            "text": preview,
            "characters": len(preview),
            "original_characters": original_characters,
            "truncated": original_characters > len(preview),
            "allow_large": bool(allow_large),
        }

    def _large_text_refusal(self, path, size, limit):
        return {
            "ok": False,
            "path": str(path.relative_to(self.workspace_root)),
            "file_type": file_type_for_path(path),
            "error_type": "file_too_large",
            "message": f"File is {size} bytes, exceeding the {limit} byte read limit.",
            "bytes": size,
            "limit_bytes": limit,
            "recommendation": "Use code_search snippets/ranges or pass allow_large=true when appropriate.",
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
