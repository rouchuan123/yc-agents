from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


STYLE_SCHEMA = {
    "type": "object",
    "properties": {
        "style_id": {"type": "string"},
        "alignment": {"type": "string"},
        "line_spacing_pt": {"type": "number"},
        "line_spacing_rule": {"type": "string"},
        "left_indent_pt": {"type": "number"},
        "right_indent_pt": {"type": "number"},
        "first_line_indent_pt": {"type": "number"},
        "space_before_pt": {"type": "number"},
        "space_after_pt": {"type": "number"},
        "keep_together": {"type": "boolean"},
        "keep_with_next": {"type": "boolean"},
        "page_break_before": {"type": "boolean"},
        "widow_control": {"type": "boolean"},
        "font_name": {"type": "string"},
        "font_size_pt": {"type": "number"},
        "bold": {"type": "boolean"},
    },
    "additionalProperties": False,
}


OPERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": [
                "replace_text",
                "replace_section",
                "insert",
                "delete",
                "move",
                "update_table",
                "delete_table_column",
                "set_style",
                "replace_image",
            ],
        },
        "target": {"type": "string"},
        "old_text": {"type": "string"},
        "new_text": {"type": "string"},
        "expected_replacements": {"type": "integer"},
        "content": {"type": "string"},
        "title": {"type": "string"},
        "type": {"type": "string"},
        "before": {"type": "string"},
        "rows": {"type": "array", "items": {"type": "array"}},
        "column": {"anyOf": [{"type": "integer"}, {"type": "string"}]},
        "style": STYLE_SCHEMA,
        "image_path": {"type": "string"},
    },
    "required": ["operation"],
    "additionalProperties": False,
}


class DocxEditTool(BaseTool):
    name = "docx_edit"
    description = (
        "Apply exact local operations to the current DOCX and create a new immutable revision. "
        "Requires the current base_revision and rejects ambiguous targets or version conflicts. "
        "Every operations[] item is one FLAT object with an operation field; never nest under "
        "set_style/replace_text/args and never use type as the operation name. "
        "Example: {'operation':'set_style','target':'body.p0010',"
        "'style':{'style_id':'Heading 1'}}. style must be an object, not a style-name string. "
        "Other operations: replace_text {old_text,new_text,expected_replacements}, "
        "replace_section {target,content,title?}, insert {target,content}, delete {target,type?}, "
        "move {target,before}, update_table {target,rows}, delete_table_column {target,column}, "
        "replace_image {target,image_path}. Prefer paragraph IDs returned by docx_verify; "
        "target tables by body.tblNNNN. Identical old_text/new_text is rejected as a no-op."
    )
    risk = "write"
    schema = ToolSchema(
        fields=[
            ToolField(name="job_id", type="str", required=True),
            ToolField(name="base_revision", type="int", required=True),
            ToolField(
                name="operations",
                type="list",
                required=True,
                json_schema={"type": "array", "items": OPERATION_SCHEMA},
                description=(
                    "Flat edit operation objects. For QA style findings, create one set_style "
                    "operation per target_ids entry and copy the finding's expected_style object."
                ),
            ),
            ToolField(name="output_name", type="str", required=False, default=""),
        ]
    )

    def __init__(self, editor):
        self.editor = editor

    def run(self, job_id, base_revision, operations, output_name=""):
        return self.editor.edit(job_id, base_revision, operations, output_name=output_name)
