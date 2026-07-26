from pathlib import Path

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocumentJobTool(BaseTool):
    name = "document_job"
    description = (
        "Create and manage the active immutable-version document authoring job. "
        "Use set_contract—not set_plan/set_outline—for table and complex-object preserve/delete/rewrite decisions. "
        "For example, preserving a table's layout while replacing its business content is "
        "contract.tables=[{element_id: 'body.tbl0000', action: 'rewrite'}]; do not put this decision in confirm. "
        "Write replacement headers/rows with document_content.upsert_section tables and target_element_id; "
        "do not rely on contract replacement_data for new jobs. "
        "Contract items use element_id; legacy id is accepted and normalized. set_contract merges decisions by "
        "element_id and only invalidates confirmation when the effective contract changes. Never repeat an unchanged "
        "set_contract after confirm_plan. confirm_plan locks the contract. Use unlock_contract only when the user "
        "explicitly changes a decision, and replace_contract only to intentionally discard all prior decisions. "
        "set_plan canonicalizes chapters to recursive sections/children and always invalidates prior plan confirmation; "
        "when it returns requires_plan_confirmation, call confirm_plan before writing content. "
        "get_active also returns current session attachments. When no job exists, use an existing template attachment; "
        "create auto-selects it when there is exactly one unique DOCX template. With no attachment, create "
        "auto-imports the single .docx in the workspace root, or takes template_path (absolute or relative to the "
        "workspace root) to import a specific file. Do not ask the user to attach again "
        "when get_active or list_attachments already returns a template. "
        "Job payloads are a lite decision view (status, pending question count and head, confirmation flags, "
        "revision counts); call get_outline when you need the full outline."
    )
    schema = ToolSchema(
        fields=[
            ToolField(name="operation", type="str", required=True),
            ToolField(name="job_id", type="str", required=False, default=""),
            ToolField(name="attachment_id", type="str", required=False, default=""),
            ToolField(name="template_path", type="str", required=False, default=""),
            ToolField(name="title", type="str", required=False, default=""),
            ToolField(name="requirements", type="dict", required=False, default={}),
            # None means "leave unchanged"; pass [] explicitly to clear the queue.
            ToolField(name="pending_questions", type="list", required=False, default=None),
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
        template_path="",
        title="",
        requirements=None,
        pending_questions=None,
        contract=None,
        outline=None,
        version=0,
    ):
        operation = str(operation).strip().lower()
        if operation == "create":
            auto_imported_from = None
            if str(template_path or "").strip():
                attachment = self._import_template_path(template_path)
            elif attachment_id:
                attachment = self.attachment_manager.get(attachment_id)
            else:
                attachment, auto_imported_from = self._select_or_discover_template()
            result = {
                "ok": True,
                "job": self.job_store.create(attachment, title=title),
                "selected_attachment": self._attachment_summary(attachment),
            }
            if auto_imported_from:
                result["auto_imported_from"] = auto_imported_from
            return result
        if operation == "get_active":
            attachments = self._attachment_summaries()
            result = {
                "ok": True,
                "job": self.job_store.summary_lite(self.job_store.get_active()),
                "attachments": attachments,
            }
            self._append_workspace_hint(result, attachments)
            return result
        if operation == "list_attachments":
            attachments = self._attachment_summaries()
            result = {"ok": True, "attachments": attachments, "count": len(attachments)}
            self._append_workspace_hint(result, attachments)
            return result
        job_id = self._resolve_job_id(job_id)
        if operation == "get":
            return {"ok": True, "job": self.job_store.summary_lite(self.job_store.get(job_id))}
        if operation == "get_outline":
            data = self.job_store.get(job_id)
            return {
                "ok": True,
                "job_id": data["id"],
                "plan_confirmed": bool(data.get("plan_confirmed")),
                "outline": data.get("outline"),
            }
        if operation == "unlock_contract":
            data = self.job_store.unlock_contract(job_id)
            return {
                "ok": True,
                "job": self.job_store.summary_lite(data),
                "requires_plan_confirmation": True,
                "next_action": "document_job.set_contract",
                "instruction": "Only unlock after the user explicitly changes a contract decision.",
                "remaining_confirm_items": self.job_store.unresolved_confirmation_items(job_id),
            }
        if operation == "update_requirements":
            data = self.job_store.update_requirements(
                job_id,
                requirements or {},
                pending_questions=pending_questions,
            )
            remaining = list(data.get("pending_questions") or [])
            return {
                "ok": True,
                "job": self.job_store.summary_lite(data),
                "pending_questions": remaining,
                "instruction": (
                    "All questions answered." if not remaining else
                    "Questions still pending block confirm_plan; ask the user, then save the "
                    "answers with update_requirements(..., pending_questions=[])."
                ),
            }
        if operation in {"set_contract", "replace_contract"}:
            data = self.job_store.set_contract(
                job_id,
                contract or {},
                replace=operation == "replace_contract",
            )
            changed = bool(data.pop("_contract_changed", False))
            requires_confirmation = not bool(data.get("plan_confirmed"))
            remaining = self.job_store.unresolved_confirmation_items(job_id)
            return {
                "ok": True,
                "job": self.job_store.summary_lite(data),
                "contract": self.job_store.get_contract(job_id),
                "contract_changed": changed,
                "requires_plan_confirmation": requires_confirmation,
                "remaining_confirm_items": remaining,
                "next_action": "document_job.confirm_plan" if requires_confirmation else "docx_generate",
                "instruction": (
                    "Contract decisions were merged by element_id. Do not call set_plan/set_outline for them, "
                    "and do not repeat set_contract when contract_changed is false."
                    + (
                        f" Still awaiting user decisions for: {remaining}."
                        if remaining
                        else " No confirmation items remain."
                    )
                ),
            }
        if operation == "set_plan":
            data = self.job_store.set_plan(job_id, outline or {})
            data = self.job_store.update(job_id, status="waiting_plan_confirmation")
            return {
                "ok": True,
                "job": self.job_store.summary_lite(data),
                # The canonical outline is echoed once so the model can
                # proof-read it before confirm_plan.
                "outline": data.get("outline"),
                "requires_plan_confirmation": True,
                "next_action": "document_job.confirm_plan",
            }
        if operation == "confirm_plan":
            try:
                data = self.job_store.confirm_plan(job_id)
            except ValueError as exc:
                if not str(exc).startswith("PENDING_QUESTIONS:"):
                    raise
                current = self.job_store.get(job_id)
                questions = list(current.get("pending_questions") or [])
                return {
                    "ok": False,
                    "error": "PENDING_QUESTIONS",
                    "error_type": "needs_user_input",
                    "requires_user_input": True,
                    "pending_questions": questions,
                    "job": self.job_store.summary_lite(current),
                    "next_action": "ask_user",
                    "instruction": (
                        "Pause this document workflow. Ask the user all pending_questions "
                        "in one concise message. Do not infer answers, call web_search, clear "
                        "the queue, or continue document tools until the user replies."
                    ),
                }
            return {
                "ok": True,
                "job": self.job_store.summary_lite(data),
                "requires_plan_confirmation": False,
                "next_action": "docx_generate",
                "instruction": "Plan confirmed. Do not call set_contract again unless the user changes a decision.",
            }
        if operation == "rollback":
            data = self.job_store.rollback(job_id, version)
            return {"ok": True, "job": self.job_store.summary_lite(data)}
        raise ValueError(f"Unsupported document_job operation: {operation}")

    def _resolve_job_id(self, job_id):
        value = str(job_id or "").strip()
        if value:
            return value
        active = self.job_store.get_active()
        if active and active.get("id"):
            return str(active["id"])
        raise ValueError(
            "No active document job is available in the current session. "
            "Call document_job.create first; it auto-discovers a single workspace-root DOCX "
            "or accepts template_path."
        )

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
            return None
        if len(unique) > 1:
            choices = ", ".join(
                f"{item['id']} ({item['name']})" for item in unique.values()
            )
            raise ValueError(
                "Multiple different DOCX templates are attached; specify attachment_id. "
                f"Candidates: {choices}"
            )
        return next(iter(unique.values()))

    def _select_or_discover_template(self):
        attachment = self._select_single_template()
        if attachment is not None:
            return attachment, None
        candidates = self._workspace_docx_candidates()
        if len(candidates) == 1:
            record = self.attachment_manager.import_file(candidates[0], role="template")
            return record, str(candidates[0])
        if candidates:
            names = ", ".join(path.name for path in candidates)
            raise ValueError(
                "The session has no template attachment and the workspace root has multiple "
                f"DOCX files: {names}. Ask the user which one is the template if unclear, then "
                'call document_job.create with template_path="<one of these file names>".'
            )
        raise ValueError(
            "No DOCX template is available: the session has no template attachment and the "
            f"workspace root ({self._workspace_root()}) has no .docx file. Ask the user where "
            "the finished Word template is, then call document_job.create with "
            'template_path="<that path>" (absolute or relative to the workspace root); '
            "the user can also run /attach template <path>."
        )

    def _import_template_path(self, template_path):
        raw = str(template_path or "").strip().strip('"')
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self._workspace_root() / path
        path = path.resolve()
        if not path.is_file():
            raise ValueError(
                f"template_path does not exist: {raw}. Pass an absolute path or a path "
                f"relative to the workspace root ({self._workspace_root()}); check the "
                "workspace_docx_candidates hint from list_attachments or ask the user "
                "for the correct file."
            )
        if path.suffix.lower() != ".docx":
            raise ValueError(
                f"template_path must point to a .docx template, got: {path.name}. Only a "
                "finished Word .docx can seed a document job; pick one from "
                "workspace_docx_candidates or ask the user for the .docx file."
            )
        return self.attachment_manager.import_file(path, role="template")

    def _workspace_root(self):
        return Path(self.job_store.workspace_root)

    def _workspace_docx_candidates(self):
        root = self._workspace_root()
        if not root.is_dir():
            return []
        return sorted(
            (
                path
                for path in root.glob("*.docx")
                if path.is_file() and not path.name.startswith("~$")
            ),
            key=lambda path: path.name,
        )

    def _append_workspace_hint(self, result, attachments):
        if any(item.get("suffix") == ".docx" for item in attachments):
            return
        result["workspace_docx_candidates"] = [
            path.name for path in self._workspace_docx_candidates()
        ]

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
