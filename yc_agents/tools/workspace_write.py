import os
import stat
from pathlib import Path
from uuid import uuid4

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class WorkspaceWriteTool(BaseTool):
    name = "workspace_write"
    description = (
        "Create or edit UTF-8 text files inside the active workspace. "
        "Supports create, write, replace, and append operations."
    )
    schema = ToolSchema(
        fields=[
            ToolField(name="file_path", type="str", required=True),
            ToolField(name="operation", type="str", required=False, default="write"),
            ToolField(name="content", type="str", required=False, default=""),
            ToolField(name="old_text", type="str", required=False, default=""),
            ToolField(name="new_text", type="str", required=False, default=""),
            ToolField(
                name="expected_replacements",
                type="int",
                required=False,
                default=1,
            ),
        ]
    )

    def __init__(self, workspace_root):
        self.workspace_root = Path(workspace_root).resolve()

    def run(
        self,
        file_path,
        operation="write",
        content="",
        old_text="",
        new_text="",
        expected_replacements=1,
    ):
        path = self._resolve_workspace_path(file_path)
        operation = str(operation or "write").strip().lower()
        if operation not in {"create", "write", "replace", "append"}:
            raise ValueError(
                "operation must be one of: create, write, replace, append"
            )

        existed = path.exists()
        if existed and not path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        replacements = 0
        if operation == "create":
            if existed:
                raise ValueError(f"File already exists: {file_path}")
            updated_text = str(content)
        elif operation == "write":
            updated_text = str(content)
        elif operation == "append":
            current_text = self._read_existing_text(path) if existed else ""
            updated_text = current_text + str(content)
        else:
            if not existed:
                raise FileNotFoundError(f"File not found in active workspace: {file_path}")
            if not old_text:
                raise ValueError("old_text is required for replace")
            if expected_replacements < 1:
                raise ValueError("expected_replacements must be at least 1")
            current_text = self._read_existing_text(path)
            replacements = current_text.count(old_text)
            if replacements != expected_replacements:
                raise ValueError(
                    "replace expected "
                    f"{expected_replacements} occurrence(s), found {replacements}"
                )
            updated_text = current_text.replace(old_text, new_text)

        self._atomic_write(path, updated_text)
        return {
            "ok": True,
            "path": str(path.relative_to(self.workspace_root)),
            "operation": operation,
            "created": not existed,
            "bytes": len(updated_text.encode("utf-8")),
            "characters": len(updated_text),
            "replacements": replacements,
            "exists": path.exists(),
        }

    def _resolve_workspace_path(self, file_path):
        raw_path = str(file_path or "").strip()
        if not raw_path:
            raise ValueError("file_path is required")

        relative_path = Path(raw_path)
        if relative_path.is_absolute():
            raise PermissionError("file_path must be relative to the active workspace")
        if any(part == ".." for part in relative_path.parts):
            raise PermissionError("file_path must not contain '..'")
        if not relative_path.name:
            raise ValueError("file_path must identify a file")

        protected_parts = {part.lower() for part in relative_path.parts}
        if protected_parts & {".git", ".ycore"}:
            raise PermissionError("Writing .git or .ycore internal files is not allowed")

        resolved = (self.workspace_root / relative_path).resolve()
        if resolved != self.workspace_root and self.workspace_root not in resolved.parents:
            raise PermissionError(f"Path escapes active workspace: {file_path}")
        if resolved == self.workspace_root:
            raise ValueError("file_path must identify a file")
        return resolved

    def _read_existing_text(self, path):
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                return handle.read()
        except UnicodeDecodeError as exc:
            raise ValueError(f"File is not valid UTF-8 text: {path.name}") from exc

    def _atomic_write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temp_path.open("x", encoding="utf-8", newline="") as handle:
                handle.write(text)
            if path.exists():
                os.chmod(temp_path, stat.S_IMODE(path.stat().st_mode))
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
