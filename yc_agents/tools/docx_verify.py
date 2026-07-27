from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocxVerifyTool(BaseTool):
    name = "docx_verify"
    description = (
        "Run deterministic DOCX fidelity checks, Microsoft Word PDF export, per-page PNG rendering, "
        "and optional MiMo vision QA for an immutable revision. "
        "mode=deterministic is fast and free; run it first after every generate/edit, and run "
        "mode=all (render + vision + publish gate) once deterministic passes. "
        "A failed check returns ok=false with error=DOCX_QA_BLOCKED plus the full findings list "
        "(anchor/page/suggested_action/category plus stable unexpected_target_ids when available) — "
        "fix findings with docx_edit using those paragraph IDs or anchors; "
        "do not regenerate an unchanged document. Only severity=blocking category=environment "
        "findings (for example Word, vision model, or PyMuPDF failures) require an environment "
        "waiver; non-blocking font warnings are disclosure-only and never stop publication. "
        "Blocking environment findings cannot be fixed by editing the document: report them to the "
        "user instead, and with the user's explicit consent operation=publish with "
        "waive_environment=true delivers anyway, recording the waived items in delivery.waivers. "
        "A successful published result "
        "returns terminal=true and next_action=final_answer: stop all tool calls for that user turn."
    )
    timeout_seconds = 600
    schema = ToolSchema(
        fields=[
            ToolField(name="job_id", type="str", required=True),
            ToolField(name="version", type="int", required=False, default=0),
            ToolField(name="mode", type="str", required=False, default="all"),
            ToolField(name="operation", type="str", required=False, default="verify"),
            ToolField(name="waive_environment", type="bool", required=False, default=False),
        ]
    )

    def __init__(self, verifier):
        self.verifier = verifier

    def run(self, job_id, version=0, mode="all", operation="verify", waive_environment=False):
        if operation not in {"verify", "publish"}:
            raise ValueError("operation must be one of: verify, publish")
        if operation == "publish":
            published = self.verifier.publish(
                job_id, version=version or None, waive_environment=bool(waive_environment)
            )
            waivers = list(published.get("waivers") or [])
            return {
                "ok": True,
                "operation": "publish",
                "version": published.get("version"),
                "published_path": published.get("published_path"),
                "already_published": bool(published.get("already_published")),
                "waivers": waivers,
                "workflow_complete": True,
                "terminal": True,
                "next_action": "final_answer",
                "instruction": (
                    "已降级发布：本轮立即停止调用任何工具并给出最终交付回复；"
                    "必须原样列出 waivers 中被豁免的环境检查项。"
                    if waivers
                    else "已发布：本轮立即停止调用任何工具并给出最终交付回复，"
                    "包含版本号与 published_path。"
                ),
            }
        if mode not in {"all", "deterministic", "render", "visual"}:
            raise ValueError("mode must be one of: all, deterministic, render, visual")
        result = self.verifier.verify(job_id, version=version or None, mode=mode)
        # Decision-minimal responses: the full report already lives on disk at
        # qa_report_path, so only what the next action needs travels back.
        if not result.get("passed"):
            blocking = [
                self._finding_summary(item)
                for item in result.get("findings", [])
                if item.get("severity") == "blocking"
            ]
            if result.get("environment_blocked"):
                next_action = "docx_verify"
                instruction = (
                    "Blocking findings include severity=blocking category=environment items "
                    "(for example Word renderer, vision model, or PyMuPDF failures). "
                    "Non-blocking font warnings do not require a waiver and must not be described "
                    "as stopping publication. Editing blocking environment findings cannot fix "
                    "them: explain them to the user and only repair category=document findings "
                    "with docx_edit. If the user cannot fix the environment and explicitly agrees, "
                    "deliver anyway with "
                    "docx_verify(operation='publish', waive_environment=true); the waived items are "
                    "recorded in delivery.waivers and must be disclosed in the delivery reply."
                )
            else:
                next_action = "docx_edit"
                instruction = (
                    "Fix each blocking finding with docx_edit on the current revision. When a "
                    "finding includes target_ids and expected_style, create one flat set_style "
                    "operation per target ID and copy expected_style as the style object; do not "
                    "use the semantic anchor as a paragraph target. Otherwise use a stable "
                    "body.pNNNN/unexpected_target_ids value when supplied. The full report is at "
                    "qa_report_path. Regenerating without changing content will be rejected "
                    "(NO_CONTENT_CHANGE). After the fix, verify deterministic first, then mode=all."
                )
            return {
                "ok": False,
                "error": "DOCX_QA_BLOCKED",
                "version": result.get("version"),
                "passed": False,
                "environment_blocked": bool(result.get("environment_blocked")),
                "findings": blocking,
                "qa_report_path": result.get("qa_report_path"),
                "next_action": next_action,
                "instruction": instruction,
            }
        warnings = [
            self._finding_summary(item)
            for item in result.get("findings", [])
            if item.get("severity") == "warning"
        ]
        delivery_ready = bool(result.get("delivery_ready"))
        published_path = result.get("published_path")
        workflow_complete = bool(delivery_ready and published_path)
        response = {
            "ok": True,
            "version": result.get("version"),
            "passed": True,
            "delivery_ready": delivery_ready,
            "published_path": published_path,
            "warning_count": result.get("warning_count", len(warnings)),
            "qa_report_path": result.get("qa_report_path"),
            "findings": warnings,
            "workflow_complete": workflow_complete,
            "terminal": workflow_complete,
            "next_action": "final_answer" if workflow_complete else "docx_verify",
            "instruction": (
                "Delivery is complete. Stop calling tools in this turn and return the final "
                "answer with version, published_path, sources, and remaining warnings. Warnings "
                "are disclosure-only after publication: do not call docx_edit, docx_generate, "
                "document_content, or docx_verify again in this turn. A later user turn may "
                "explicitly request revisions, which must create and fully verify a new version."
                if workflow_complete
                else "This partial QA mode did not publish the document. Continue with "
                "docx_verify(mode='all') on the same version; do not claim delivery yet."
            ),
        }
        return response

    @staticmethod
    def _finding_summary(item):
        result = {
            "anchor": str(item.get("anchor") or ""),
            "issue": str(item.get("issue") or ""),
            "suggested_action": str(item.get("suggested_action") or ""),
            "category": str(item.get("category") or "document"),
        }
        for key in (
            "page",
            "expected_count",
            "actual_count",
            "unexpected_target_ids",
            "target_ids",
            "expected_style",
            "mismatched_fields",
            "diagnostics",
        ):
            if key in item:
                result[key] = item.get(key)
        return result
