from pathlib import Path

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool
from yc_agents.tools.readable_files import (
    DEFAULT_EXCLUDED_DIRS,
    file_type_for_path,
    is_readable_workspace_file,
)


class WorkspaceFilesTool(BaseTool):
    name = "workspace_files"
    description = "List readable files in the active workspace."
    schema = ToolSchema(
        fields=[
            ToolField(name="pattern", type="str", required=False, default="*"),
        ]
    )

    def __init__(self, workspace_root, excluded_dirs=None):
        self.workspace_root = Path(workspace_root).resolve()
        self.excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
        self.excluded_dirs.update(excluded_dirs or set())

    def _is_excluded(self, path):
        relative_parts = path.relative_to(self.workspace_root).parts
        return any(part in self.excluded_dirs for part in relative_parts)

    def run(self, pattern="*"):
        files = []
        for path in sorted(self.workspace_root.rglob(pattern or "*")):
            if not path.is_file():
                continue
            if self._is_excluded(path):
                continue
            if not is_readable_workspace_file(path):
                continue
            files.append(
                {
                    "path": str(path.relative_to(self.workspace_root)),
                    "name": path.name,
                    "file_type": file_type_for_path(path),
                    "bytes": path.stat().st_size,
                }
            )

        return {
            "workspace": str(self.workspace_root),
            "count": len(files),
            "files": files,
        }
