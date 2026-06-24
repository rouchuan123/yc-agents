import tempfile
import unittest
from pathlib import Path

from yc_agents.docx_format.auditor import audit_docx
from yc_agents.docx_format.formatter import format_docx
from yc_agents.docx_format.models import DocumentBlock, DocumentModel, UnsupportedObject
from yc_agents.docx_format.template import load_builtin_template


class TestDocxFormatAuditor(unittest.TestCase):
    def test_audit_passes_generated_document(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "normalized.docx"
            rules = load_builtin_template("report-standard")
            model = DocumentModel(
                source_path="draft.docx",
                blocks=[
                    DocumentBlock(id="b1", type="heading", text="Project Overview", level=1),
                    DocumentBlock(id="b2", type="paragraph", text="Body paragraph."),
                ],
            )
            format_docx(model, rules, output_path)

            report = audit_docx(output_path, rules, source_model=model)

            self.assertEqual(report.status, "passed")
            self.assertEqual(
                {check.name: check.status for check in report.checks}["file_exists"],
                "passed",
            )

    def test_audit_reports_unsupported_objects_as_warning(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "normalized.docx"
            rules = load_builtin_template("report-standard")
            model = DocumentModel(
                source_path="draft.docx",
                unsupported_objects=[
                    UnsupportedObject(type="chart", location="word/charts/chart1.xml")
                ],
            )
            format_docx(model, rules, output_path)

            report = audit_docx(output_path, rules, source_model=model)

            self.assertEqual(report.status, "passed_with_warnings")
            self.assertIn("unsupported_objects", [check.name for check in report.checks])


if __name__ == "__main__":
    unittest.main()
