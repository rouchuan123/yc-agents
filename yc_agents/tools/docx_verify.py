from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools.base import BaseTool


class DocxVerifyTool(BaseTool):
    name = "docx_verify"
    description = (
        "Run deterministic DOCX fidelity checks, Microsoft Word PDF export, per-page PNG rendering, "
        "and optional MiMo vision QA for an immutable revision."
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
        return self.verifier.verify(job_id, version=version or None, mode=mode)
