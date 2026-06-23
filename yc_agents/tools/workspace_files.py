from pathlib import Path

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


SUPPORTED_SUFFIXES = {".docx", ".pdf", ".md", ".txt"}


class WorkspaceFilesTool(BaseTool):
    name = "workspace_files"
    description = "List readable files in the active workspace."
    schema = ToolSchema(
        fields=[
            ToolField(name="pattern", type="str", required=False, default="*"),
        ]
    )

    def __init__(self, workspace_root):
        self.workspace_root = Path(workspace_root).resolve()

    def run(self, pattern="*"):
        files = []
        for path in sorted(self.workspace_root.rglob(pattern or "*")):
            if not path.is_file():
                continue
            if ".ycore" in path.relative_to(self.workspace_root).parts:
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            files.append(
                {
                    "path": str(path.relative_to(self.workspace_root)),
                    "name": path.name,
                    "file_type": path.suffix.lower().lstrip("."),
                    "bytes": path.stat().st_size,
                }
            )

        return {
            "workspace": str(self.workspace_root),
            "count": len(files),
            "files": files,
        }
