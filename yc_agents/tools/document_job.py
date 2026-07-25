from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocumentJobTool(BaseTool):
    name = "document_job"
    description = (
        "Create and manage the active immutable-version document authoring job. "
        "Use set_contract—not set_plan/set_outline—for table and complex-object preserve/delete/rewrite decisions. "
        "Contract items use element_id; legacy id is accepted and normalized. set_contract merges decisions by "
        "element_id and only invalidates confirmation when the effective contract changes. Never repeat an unchanged "
        "set_contract after confirm_plan. confirm_plan locks the contract. Use unlock_contract only when the user "
        "explicitly changes a decision, and replace_contract only to intentionally discard all prior decisions. "
        "set_plan canonicalizes chapters to recursive sections/children and always invalidates prior plan confirmation; "
        "when it returns requires_plan_confirmation, call confirm_plan before writing content. "
        "get_active also returns current session attachments. When no job exists, use an existing template attachment; "
        "create auto-selects it when there is exactly one unique DOCX template. Do not ask the user to attach again "
        "when get_active or list_attachments already returns a template."
    )
    schema = ToolSchema(
        fields=[
            ToolField(name="operation", type="str", required=True),
            ToolField(name="job_id", type="str", required=False, default=""),
            ToolField(name="attachment_id", type="str", required=False, default=""),
            ToolField(name="title", type="str", required=False, default=""),
            ToolField(name="requirements", type="dict", required=False, default={}),
            ToolField(name="pending_questions", type="list", required=False, default=[]),
            ToolField(name="contract", type="dict", required=False, default={}),
            ToolField(name="outline", type="dict", required=False, default={}),
            ToolField(name="version", type="int", required=False, default=0),
        ]
    )

    def __init__(self, job_store, attachment_manager):
        self.job_store = job_store
        self.attachment_manager = attachment_manager

    def run(
        self,
        operation,
        job_id="",
        attachment_id="",
        title="",
        requirements=None,
        pending_questions=None,
        contract=None,
        outline=None,
        version=0,
    ):
        operation = str(operation).strip().lower()
        if operation == "create":
            if not attachment_id:
                attachment = self._select_single_template()
            else:
                attachment = self.attachment_manager.get(attachment_id)
            return {
                "ok": True,
                "job": self.job_store.create(attachment, title=title),
                "selected_attachment": self._attachment_summary(attachment),
            }
        if operation == "get_active":
            return {
                "ok": True,
                "job": self.job_store.summary(self.job_store.get_active()),
                "attachments": self._attachment_summaries(),
            }
        if operation == "list_attachments":
            attachments = self._attachment_summaries()
            return {"ok": True, "attachments": attachments, "count": len(attachments)}
        if operation == "get":
            return {"ok": True, "job": self.job_store.summary(self.job_store.get(job_id))}
        if operation == "unlock_contract":
            data = self.job_store.unlock_contract(job_id)
            return {
                "ok": True,
                "job": self.job_store.summary(data),
                "requires_plan_confirmation": True,
                "next_action": "document_job.set_contract",
                "instruction": "Only unlock after the user explicitly changes a contract decision.",
            }
        if operation == "update_requirements":
            data = self.job_store.update_requirements(
                job_id,
                requirements or {},
                pending_questions=pending_questions,
            )
            return {"ok": True, "job": self.job_store.summary(data)}
        if operation in {"set_contract", "replace_contract"}:
            data = self.job_store.set_contract(
                job_id,
                contract or {},
                replace=operation == "replace_contract",
            )
            changed = bool(data.pop("_contract_changed", False))
            requires_confirmation = not bool(data.get("plan_confirmed"))
            return {
                "ok": True,
                "job": self.job_store.summary(data),
                "contract": self.job_store.get_contract(job_id),
                "contract_changed": changed,
                "requires_plan_confirmation": requires_confirmation,
                "next_action": "document_job.confirm_plan" if requires_confirmation else "docx_generate",
                "instruction": (
                    "Contract decisions were merged by element_id. Do not call set_plan/set_outline for them, "
                    "and do not repeat set_contract when contract_changed is false."
                ),
            }
        if operation == "set_plan":
            data = self.job_store.set_plan(job_id, outline or {})
            data = self.job_store.update(job_id, status="waiting_plan_confirmation")
            return {
                "ok": True,
                "job": self.job_store.summary(data),
                "requires_plan_confirmation": True,
                "next_action": "document_job.confirm_plan",
            }
        if operation == "confirm_plan":
            data = self.job_store.confirm_plan(job_id)
            return {
                "ok": True,
                "job": self.job_store.summary(data),
                "requires_plan_confirmation": False,
                "next_action": "docx_generate",
                "instruction": "Plan confirmed. Do not call set_contract again unless the user changes a decision.",
            }
        if operation == "rollback":
            data = self.job_store.rollback(job_id, version)
            return {"ok": True, "job": self.job_store.summary(data)}
        raise ValueError(f"Unsupported document_job operation: {operation}")

    def _select_single_template(self):
        attachments = self.attachment_manager.list()
        candidates = [
            item
            for item in attachments
            if item.get("suffix") == ".docx" and item.get("role") == "template"
        ]
        if not candidates:
            candidates = [
                item
                for item in attachments
                if item.get("suffix") == ".docx" and item.get("role") == "auto"
            ]
        unique = {}
        for item in candidates:
            unique[item.get("sha256") or item["id"]] = item
        if not unique:
            raise ValueError(
                "No DOCX template attachment is available in the current session. "
                "Use /attach template <path> once."
            )
        if len(unique) > 1:
            choices = ", ".join(
                f"{item['id']} ({item['name']})" for item in unique.values()
            )
            raise ValueError(
                "Multiple different DOCX templates are attached; specify attachment_id. "
                f"Candidates: {choices}"
            )
        return next(iter(unique.values()))

    def _attachment_summaries(self):
        return [
            self._attachment_summary(item)
            for item in self.attachment_manager.list()
        ]

    @staticmethod
    def _attachment_summary(item):
        return {
            "id": item.get("id"),
            "role": item.get("role"),
            "name": item.get("name"),
            "suffix": item.get("suffix"),
            "bytes": item.get("bytes"),
            "sha256": item.get("sha256"),
            "created_at": item.get("created_at"),
        }
