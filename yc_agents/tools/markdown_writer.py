from pathlib import Path

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class MarkdownWriterTool(BaseTool):
    name = "markdown_writer"
    description = "Write Markdown content to an output file."
    schema = ToolSchema(
        fields=[
            ToolField(name="file_name", type="str", required=True),
            ToolField(name="content", type="str", required=True),
        ]
    )

    def __init__(self, output_dir="outputs"):
        self.output_dir = Path(output_dir)

    def run(self, file_name, content):
        if content is None:
            raise ValueError("content is required")

        path = self._build_path(file_name)
        text = str(content)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

        return {
            "path": str(path),
            "bytes": len(text.encode("utf-8")),
            "exists": path.exists(),
        }

    def _build_path(self, file_name):
        if not file_name or not str(file_name).strip():
            raise ValueError("file_name is required")

        relative_path = Path(str(file_name).strip())

        if relative_path.is_absolute():
            raise ValueError("file_name must be a project-relative path")

        if ".." in relative_path.parts:
            raise ValueError("file_name must not contain '..'")

        if relative_path.suffix.lower() != ".md":
            relative_path = Path(str(relative_path) + ".md")

        return self.output_dir / relative_path
