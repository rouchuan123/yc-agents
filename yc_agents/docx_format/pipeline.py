import json
from pathlib import Path

from yc_agents.docx_format.analyzer import analyze_docx
from yc_agents.docx_format.auditor import audit_docx
from yc_agents.docx_format.formatter import format_docx
from yc_agents.docx_format.models import NormalizationOutput
from yc_agents.docx_format.template import extract_template_rules, load_builtin_template


def normalize_docx(
    source_path,
    output_dir,
    template_name="report-standard",
    template_path=None,
    output_name="normalized",
):
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Source DOCX not found: {source}")
    if source.suffix.lower() != ".docx":
        raise ValueError(f"Expected source .docx, got: {source}")

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    media_dir = output_root / "media"
    model = analyze_docx(source, media_output_dir=media_dir)
    rules = (
        extract_template_rules(template_path)
        if template_path
        else load_builtin_template(template_name)
    )

    safe_name = _safe_output_name(output_name)
    output_docx = output_root / f"{safe_name}.docx"
    audit_json = output_root / f"{safe_name}.audit.json"
    audit_report = output_root / f"{safe_name}.audit.md"

    format_docx(model, rules, output_docx)
    report = audit_docx(output_docx, rules, source_model=model)
    audit_json.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    audit_report.write_text(_render_markdown_report(report), encoding="utf-8")

    return NormalizationOutput(
        output_docx=output_docx,
        audit_report=audit_report,
        audit_json=audit_json,
    )


def _safe_output_name(value):
    text = str(value or "normalized").strip()
    text = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in text)
    return text or "normalized"


def _render_markdown_report(report):
    lines = [
        "# Document Format Audit",
        "",
        f"Status: `{report.status}`",
        f"Output: `{report.output_docx}`",
        "",
        "| Check | Status | Message |",
        "| --- | --- | --- |",
    ]
    for check in report.checks:
        lines.append(f"| {check.name} | {check.status} | {check.message} |")
    lines.append("")
    return "\n".join(lines)
