from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocxEditTool(BaseTool):
    name = "docx_edit"
    description = (
        "Apply exact local operations to the current DOCX and create a new immutable revision. "
        "Requires the current base_revision and rejects ambiguous targets or version conflicts. "
        "Operations: replace_text {old_text,new_text,expected_replacements=occurrence count}, "
        "replace_section {target,content,title?}, insert {target,content}, delete {target,type?}, "
        "move {target,before}, update_table {target,rows=all rows incl. header}, "
        "delete_table_column {target,column}, set_style {target,style}, replace_image {target,image_path}. "
        "Target tables by element id (body.tbl0000) or unique cell text; paragraphs by unique text or body.pNNNN."
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
