from pathlib import Path

from yc_agents.docx_format.pipeline import normalize_docx
from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocxFormatNormalizerTool(BaseTool):
    name = "docx_format_normalizer"
    description = "Normalize a workspace DOCX draft using a built-in or uploaded DOCX template."
    schema = ToolSchema(
        fields=[
            ToolField(name="source_file", type="str", required=True),
            ToolField(
                name="template_name",
                type="str",
                required=False,
                default="report-standard",
            ),
            ToolField(name="template_file", type="str", required=False, default=""),
            ToolField(name="output_name", type="str", required=False, default="normalized"),
        ]
    )

    def __init__(self, workspace_root, output_dir=None):
        self.workspace_root = Path(workspace_root).resolve()
        self.output_dir = (
            Path(output_dir)
            if output_dir
            else self.workspace_root / ".ycore" / "docx-format"
        )

    def run(
        self,
        source_file,
        template_name="report-standard",
        template_file="",
        output_name="normalized",
    ):
        source_path = self._resolve_workspace_file(source_file)
        template_path = self._resolve_workspace_file(template_file) if template_file else None
        output = normalize_docx(
            source_path=source_path,
            output_dir=self.output_dir,
            template_name=template_name or "report-standard",
            template_path=template_path,
            output_name=output_name or "normalized",
        )
        return {
            "ok": True,
            "template": template_name or "report-standard",
            "output_docx": str(output.output_docx.relative_to(self.workspace_root)),
            "audit_report": str(output.audit_report.relative_to(self.workspace_root)),
            "audit_json": str(output.audit_json.relative_to(self.workspace_root)),
        }

    def _resolve_workspace_file(self, file_path):
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
