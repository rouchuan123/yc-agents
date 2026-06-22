from pathlib import Path
import contextlib
import io


SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx", ".pdf"}
TEXT_EXTENSIONS = {".md", ".txt"}
SUMMARY_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_DOCUMENT_CONTEXT_CHARS = 12000
MAX_DOCUMENT_PREVIEW_CHARS = 40000


class DocumentService:
    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        self.documents_root = self.project_root / "documents"

    def scan(self):
        if not self.documents_root.exists():
            return []

        items = []
        for path in sorted(self.documents_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            items.append(
                {
                    "name": path.name,
                    "relative_path": self._relative(path),
                    "extension": path.suffix.lower(),
                    "size": path.stat().st_size,
                }
            )
        return items

    def preview(self, relative_path):
        path = self._resolve_document_path(relative_path)

        if path.suffix.lower() in TEXT_EXTENSIONS:
            return {
                "kind": "text",
                "relative_path": self._relative(path),
                "content": path.read_text(encoding="utf-8"),
            }

        if path.suffix.lower() == ".pdf":
            content = self._read_pdf_text(path)
            if content:
                return {
                    "kind": "text",
                    "relative_path": self._relative(path),
                    "content": content[:MAX_DOCUMENT_PREVIEW_CHARS],
                }

        return {
            "kind": "binary",
            "relative_path": self._relative(path),
            "content": "",
        }

    def build_context_summary(self, max_chars=MAX_DOCUMENT_CONTEXT_CHARS):
        items = self.scan()
        if not items:
            return "项目资料目录 documents 目前没有可读取资料。"

        parts = ["项目资料目录 documents 中的资料："]
        remaining = max_chars

        for item in items:
            header = f"- {item['relative_path']} ({item['extension']}, {item['size']} bytes)"
            parts.append(header)
            remaining -= len(header)
            if remaining <= 0:
                break

            if item["extension"] not in SUMMARY_EXTENSIONS:
                continue

            try:
                preview = self.preview(item["relative_path"])
            except Exception as exc:
                snippet = f"  摘要读取失败：{exc}"
            else:
                content = preview.get("content", "").strip()
                snippet = f"  摘要：{content[: min(1200, max(0, remaining))]}" if content else "  摘要：暂无可抽取文本"

            parts.append(snippet)
            remaining -= len(snippet)
            if remaining <= 0:
                break

        return "\n".join(parts)

    def _resolve_document_path(self, relative_path):
        path = (self.project_root / relative_path).resolve()
        if not self._is_relative_to(path, self.documents_root.resolve()):
            raise ValueError(f"Path is outside documents directory: {relative_path}")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(relative_path)
        return path

    def _relative(self, path):
        return path.resolve().relative_to(self.project_root).as_posix()

    def _read_pdf_text(self, path):
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""

        try:
            with contextlib.redirect_stderr(io.StringIO()):
                reader = PdfReader(str(path))
            pages = []
            for page in reader.pages:
                with contextlib.redirect_stderr(io.StringIO()):
                    text = page.extract_text() or ""
                if text.strip():
                    pages.append(text.strip())
            return "\n\n".join(pages)
        except Exception:
            return ""

    def _is_relative_to(self, path, parent):
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False
