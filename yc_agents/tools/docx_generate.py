from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocxGenerateTool(BaseTool):
    name = "docx_generate"
    description = "Generate a new immutable DOCX revision from the finished template copy and completed section content."
    schema = ToolSchema(
        fields=[
            ToolField(name="job_id", type="str", required=True),
            ToolField(name="output_name", type="str", required=False, default=""),
        ]
    )

    def __init__(self, builder):
        self.builder = builder

    def run(self, job_id, output_name=""):
        return self.builder.generate(job_id, output_name=output_name)
