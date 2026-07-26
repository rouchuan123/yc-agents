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
        "(anchor/page/suggested_action/category) — fix findings with docx_edit using those anchors; "
        "do not regenerate an unchanged document. category=environment findings (fonts, Word, vision "
        "model, PyMuPDF) cannot be fixed by editing the document: report them to the user instead."
    )
    timeout_seconds = 600
    schema = ToolSchema(
        fields=[
            ToolField(name="job_id", type="str", required=True),
            ToolField(name="version", type="int", required=False, default=0),
            ToolField(name="mode", type="str", required=False, default="all"),
        ]
    )

    def __init__(self, verifier):
        self.verifier = verifier

    def run(self, job_id, version=0, mode="all"):
        if mode not in {"all", "deterministic", "render", "visual"}:
            raise ValueError("mode must be one of: all, deterministic, render, visual")
        result = self.verifier.verify(job_id, version=version or None, mode=mode)
        if not result.get("passed"):
            blocking = [
                item
                for item in result.get("findings", [])
                if item.get("severity") == "blocking"
            ]
            issues = list(dict.fromkeys(str(item.get("issue") or "") for item in blocking))
            if result.get("environment_blocked"):
                instruction = (
                    "Blocking findings include category=environment items (fonts, Word renderer, "
                    "vision model, PyMuPDF). Editing the document cannot fix those: explain them to "
                    "the user and only repair the category=document findings with docx_edit."
                )
            else:
                instruction = (
                    "Read findings[] and fix each blocking item with docx_edit on the current "
                    "revision, using the finding's anchor/page as the target. Regenerating without "
                    "changing content will be rejected (NO_CONTENT_CHANGE). After the fix, verify "
                    "deterministic first, then mode=all."
                )
            return {
                **result,
                "ok": False,
                "error": "DOCX_QA_BLOCKED",
                "blocking_issues": issues,
                "next_action": "docx_edit",
                "instruction": instruction,
            }
        return {**result, "ok": True}
