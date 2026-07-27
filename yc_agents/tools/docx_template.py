from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocxTemplateAnalyzerTool(BaseTool):
    name = "docx_template_analyzer"
    description = (
        "Analyze an attached finished DOCX template into exact effective formatting, sections, "
        "styles, numbering, tables, headers, footers, images, fields, and semantic format clusters. "
        "Analysis is idempotent per template: re-running on the same template returns the cached "
        "summary without resetting job state, so call it once per job."
    )
    schema = ToolSchema(fields=[ToolField(name="job_id", type="str", required=True)])

    def __init__(self, analyzer):
        self.analyzer = analyzer

    def run(self, job_id):
        return self.analyzer.analyze(job_id)


class DocxTemplateQueryTool(BaseTool):
    name = "docx_template_query"
    description = (
        "Query elements from an analyzed DOCX template without loading the full specification. "
        "Role/part queries return a compact text+role view by default; fetch one element_id or "
        "pass detail=true for full formatting. Output is hard-capped, so keep limit small and "
        "narrow queries instead of dumping the whole body. Common aliases are supported: "
        "role=heading returns heading_1/heading_2/etc.; part=body selects word/document.xml. "
        "Use role=table for tables. Never read or search template-spec.json directly."
    )
    schema = ToolSchema(
        fields=[
            ToolField(name="job_id", type="str", required=True),
            ToolField(name="role", type="str", required=False, default=""),
            ToolField(name="element_id", type="str", required=False, default=""),
            ToolField(name="part", type="str", required=False, default=""),
            ToolField(name="limit", type="int", required=False, default=20),
            ToolField(name="detail", type="bool", required=False, default=False),
        ]
    )

    def __init__(self, analyzer):
        self.analyzer = analyzer

    def run(self, job_id, role="", element_id="", part="", limit=20, detail=False):
        return self.analyzer.query(
            job_id, role=role, element_id=element_id, part=part, limit=limit, detail=detail
        )
