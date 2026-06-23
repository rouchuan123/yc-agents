from pathlib import Path


SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx"}
TEXT_EXTENSIONS = {".md", ".txt"}


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

        return {
            "kind": "binary",
            "relative_path": self._relative(path),
            "content": "",
        }

    def _resolve_document_path(self, relative_path):
        path = (self.project_root / relative_path).resolve()
        if not self._is_relative_to(path, self.documents_root.resolve()):
            raise ValueError(f"Path is outside documents directory: {relative_path}")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(relative_path)
        return path

    def _relative(self, path):
        return path.resolve().relative_to(self.project_root).as_posix()

    def _is_relative_to(self, path, parent):
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False
