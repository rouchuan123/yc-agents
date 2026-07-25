from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocumentContentTool(BaseTool):
    name = "document_content"
    description = (
        "Persist a recursive confirmed outline and draft long documents section by section before DOCX generation. "
        "set_outline invalidates prior confirmation; call document_job.confirm_plan exactly once after the final outline. "
        "Never retry upsert_section after PLAN_NOT_CONFIRMED until that confirmation succeeds. "
        "upsert_section returns a compact summary, not the full body; use get_section only when body text is needed."
    )
    schema = ToolSchema(
        fields=[
            ToolField(name="operation", type="str", required=True),
            ToolField(name="job_id", type="str", required=True),
            ToolField(name="outline", type="dict", required=False, default={}),
            ToolField(name="section_id", type="str", required=False, default=""),
            ToolField(name="title", type="str", required=False, default=""),
            ToolField(name="content", type="str", required=False, default=""),
            ToolField(name="source_ids", type="list", required=False, default=[]),
            ToolField(name="fact_status", type="str", required=False, default="draft"),
            ToolField(name="target_role", type="str", required=False, default=""),
            ToolField(name="tables", type="list", required=False, default=[]),
        ]
    )

    def __init__(self, content_store):
        self.content_store = content_store

    def run(
        self,
        operation,
        job_id,
        outline=None,
        section_id="",
        title="",
        content="",
        source_ids=None,
        fact_status="draft",
        target_role="",
        tables=None,
    ):
        operation = str(operation).strip().lower()
        if operation == "set_outline":
            return {
                "ok": True,
                "outline": self.content_store.set_outline(job_id, outline or {}),
                "requires_plan_confirmation": True,
                "next_action": "document_job.confirm_plan",
            }
        if operation == "upsert_section":
            result = self.content_store.upsert_section(
                job_id,
                section_id,
                title,
                content,
                source_ids=source_ids,
                fact_status=fact_status,
                target_role=target_role,
                tables=tables,
            )
            section = result["section"]
            missing = self.content_store.get_missing(job_id)
            return {
                "ok": True,
                "section": {
                    "id": section["id"],
                    "title": section["title"],
                    "characters": len(section.get("content") or ""),
                    "source_ids": list(section.get("source_ids") or []),
                    "fact_status": section.get("fact_status"),
                    "target_role": section.get("target_role"),
                    "level": section.get("level"),
                    "tables": len(section.get("tables") or []),
                },
                "path": result["path"],
                "remaining": len(missing["missing"]),
                "complete": missing["complete"],
            }
        if operation == "get_missing":
            return {"ok": True, **self.content_store.get_missing(job_id)}
        if operation == "get_section":
            return {"ok": True, "section": self.content_store.get_section(job_id, section_id)}
        raise ValueError(f"Unsupported document_content operation: {operation}")
