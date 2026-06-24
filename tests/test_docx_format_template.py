import unittest

from yc_agents.docx_format.models import (
    AuditCheck,
    DocumentBlock,
    DocumentModel,
    TemplateRules,
)
from yc_agents.docx_format.template import load_builtin_template


class TestDocxFormatModelsAndTemplates(unittest.TestCase):
    def test_document_model_groups_blocks_by_type(self):
        model = DocumentModel(
            source_path="draft.docx",
            blocks=[
                DocumentBlock(id="b1", type="heading", text="Chapter 1", level=1),
                DocumentBlock(id="b2", type="paragraph", text="Body"),
                DocumentBlock(id="b3", type="table", rows=[["A", "B"]]),
            ],
        )

        self.assertEqual(
            [block.text for block in model.blocks_by_type("heading")],
            ["Chapter 1"],
        )
        self.assertEqual(len(model.blocks_by_type("table")), 1)

    def test_builtin_report_standard_contains_required_rules(self):
        rules = load_builtin_template("report-standard")

        self.assertIsInstance(rules, TemplateRules)
        self.assertEqual(rules.name, "report-standard")
        self.assertEqual(rules.page["size"], "A4")
        self.assertEqual(rules.page["margins_cm"]["top"], 2.54)
        self.assertEqual(rules.styles["body"]["font_size_pt"], 12)
        self.assertEqual(rules.styles["heading_1"]["outline_level"], 1)
        self.assertTrue(rules.table_of_contents["enabled"])
        self.assertTrue(rules.page_numbers["enabled"])

    def test_audit_check_dict_shape(self):
        check = AuditCheck(name="page_margins", status="passed", message="ok")

        self.assertEqual(
            check.to_dict(),
            {"name": "page_margins", "status": "passed", "message": "ok"},
        )


if __name__ == "__main__":
    unittest.main()
