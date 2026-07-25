from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocumentSourceTool(BaseTool):
    name = "document_source"
    description = (
        "Discover workspace reference candidates, record user confirmation, build a job-local BM25 index, "
        "search confirmed sources, or record a web source. Never ingest unconfirmed workspace files. "
        "discover excludes the template by default; set include_template only after the user explicitly requests "
        "using old template content as evidence."
    )
    schema = ToolSchema(
        fields=[
            ToolField(name="operation", type="str", required=True),
            ToolField(name="job_id", type="str", required=True),
            ToolField(name="query", type="str", required=False, default=""),
            ToolField(name="source_ids", type="list", required=False, default=[]),
            ToolField(name="source", type="dict", required=False, default={}),
            ToolField(name="top_k", type="int", required=False, default=5),
            ToolField(name="max_results", type="int", required=False, default=20),
            ToolField(name="include_template", type="bool", required=False, default=False),
        ]
    )

    def __init__(self, source_service):
        self.source_service = source_service

    def run(
        self,
        operation,
        job_id,
        query="",
        source_ids=None,
        source=None,
        top_k=5,
        max_results=20,
        include_template=False,
    ):
        operation = str(operation).strip().lower()
        if operation == "discover":
            return self.source_service.discover(
                job_id,
                query=query,
                max_results=max_results,
                include_template=include_template,
            )
        if operation == "confirm":
            return self.source_service.confirm(job_id, source_ids or [])
        if operation == "ingest":
            return self.source_service.ingest(job_id)
        if operation == "search":
            return self.source_service.search(job_id, query=query, top_k=top_k)
        if operation == "record_web":
            return {"ok": True, "source": self.source_service.record_web(job_id, source or {})}
        raise ValueError(f"Unsupported document_source operation: {operation}")
