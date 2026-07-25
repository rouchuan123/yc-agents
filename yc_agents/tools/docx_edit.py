from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocxEditTool(BaseTool):
    name = "docx_edit"
    description = (
        "Apply exact local operations to the current DOCX and create a new immutable revision. "
        "Requires the current base_revision and rejects ambiguous targets or version conflicts."
    )
    schema = ToolSchema(
        fields=[
            ToolField(name="job_id", type="str", required=True),
            ToolField(name="base_revision", type="int", required=True),
            ToolField(name="operations", type="list", required=True),
            ToolField(name="output_name", type="str", required=False, default=""),
        ]
    )

    def __init__(self, editor):
        self.editor = editor

    def run(self, job_id, base_revision, operations, output_name=""):
        return self.editor.edit(job_id, base_revision, operations, output_name=output_name)
