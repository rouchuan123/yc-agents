from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocxTemplateAnalyzerTool(BaseTool):
    name = "docx_template_analyzer"
    description = (
        "Analyze an attached finished DOCX template into exact effective formatting, sections, "
        "styles, numbering, tables, headers, footers, images, fields, and semantic format clusters."
    )
    schema = ToolSchema(fields=[ToolField(name="job_id", type="str", required=True)])

    def __init__(self, analyzer):
        self.analyzer = analyzer

    def run(self, job_id):
        return self.analyzer.analyze(job_id)


class DocxTemplateQueryTool(BaseTool):
    name = "docx_template_query"
    description = "Query exact formatting or elements from an analyzed DOCX template without loading the full specification."
    schema = ToolSchema(
        fields=[
            ToolField(name="job_id", type="str", required=True),
            ToolField(name="role", type="str", required=False, default=""),
            ToolField(name="element_id", type="str", required=False, default=""),
            ToolField(name="part", type="str", required=False, default=""),
            ToolField(name="limit", type="int", required=False, default=20),
        ]
    )

    def __init__(self, analyzer):
        self.analyzer = analyzer

    def run(self, job_id, role="", element_id="", part="", limit=20):
        return self.analyzer.query(job_id, role=role, element_id=element_id, part=part, limit=limit)
