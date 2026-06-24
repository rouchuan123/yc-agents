import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yc_agents.skills.loader import SkillLoader


class TestSkillLoader(unittest.TestCase):
    def test_load_all_reads_only_document_format_normalizer_skill(self):
        loader = SkillLoader("skills")

        skills = loader.load_all()

        self.assertEqual([skill.name for skill in skills], ["document-format-normalizer"])
        skill = skills[0]
        self.assertIn("docx_format_normalizer", skill.allowed_tools)
        self.assertIn("Word", skill.description)
        self.assertIn("Word 文档格式调整", skill.body)
        self.assertEqual(skill.path, "skills/document-format-normalizer")

    def test_document_format_skill_does_not_allow_web_search(self):
        skill = SkillLoader("skills").load_all()[0]

        self.assertEqual(skill.name, "document-format-normalizer")
        self.assertNotIn("web_search", skill.allowed_tools)

    def test_load_all_discovers_nested_skill_related_files(self):
        loader = SkillLoader("skills")

        skill = loader.load_all()[0]

        self.assertTrue(
            any(path.endswith("references/template-schema.md") for path in skill.references)
        )
        self.assertTrue(
            any(
                path.endswith("references/builtin-templates/report-standard.md")
                for path in skill.references
            )
        )
        self.assertTrue(
            any(path.endswith("assets/templates/.gitkeep") for path in skill.assets)
        )
        self.assertTrue(
            any(
                path.endswith("scripts/docx_format/cli.py")
                for path in [script["path"] for script in skill.scripts]
            )
        )

    def test_document_format_skill_support_files_are_chinese_friendly(self):
        skill_dir = Path("skills") / "document-format-normalizer"

        template_schema = (
            skill_dir / "references" / "template-schema.md"
        ).read_text(encoding="utf-8")
        report_standard = (
            skill_dir / "references" / "builtin-templates" / "report-standard.md"
        ).read_text(encoding="utf-8")

        self.assertIn("# 模板规则结构", template_schema)
        self.assertIn("给后续修改者看的规则分组", template_schema)
        self.assertIn("页边距", template_schema)
        self.assertIn("正文", template_schema)
        self.assertNotIn("# Template Rule Schema", template_schema)

        self.assertIn("# 报告标准模板", report_standard)
        self.assertIn("页面设置", report_standard)
        self.assertIn("正文", report_standard)
        self.assertIn("标题", report_standard)
        self.assertNotIn("# Report Standard Template", report_standard)

    def test_document_format_skill_cli_help_is_chinese_friendly(self):
        cli_path = (
            Path("skills")
            / "document-format-normalizer"
            / "scripts"
            / "docx_format"
            / "cli.py"
        )
        spec = importlib.util.spec_from_file_location(
            "skill_docx_format_cli", cli_path
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        help_output = io.StringIO()
        with contextlib.redirect_stdout(help_output):
            with self.assertRaises(SystemExit) as caught:
                module.main(["--help"])

        self.assertEqual(caught.exception.code, 0)
        help_text = help_output.getvalue()
        self.assertIn("规范化 DOCX 草稿格式", help_text)
        self.assertIn("源 Word .docx 文件路径", help_text)
        self.assertIn("输出目录", help_text)
        self.assertIn("内置模板名称", help_text)
        self.assertNotIn("Normalize a DOCX draft", help_text)

    def test_load_one_reads_expanded_metadata(self):
        with TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "document-format-normalizer"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: document-format-normalizer",
                        "description: Normalize Word documents",
                        "triggers:",
                        "  - Word 格式调整",
                        "  - docx formatting",
                        "inputs:",
                        "  - source_docx",
                        "outputs:",
                        "  - normalized_docx",
                        "allowed_tools:",
                        "  - docx_format_normalizer",
                        "examples:",
                        "  - 帮我调整 draft.docx 的格式",
                        "---",
                        "",
                        "# Document Format Normalizer",
                    ]
                ),
                encoding="utf-8",
            )

            skill = SkillLoader(tmpdir).load_one(skill_dir)

            self.assertEqual(skill.triggers, ["Word 格式调整", "docx formatting"])
            self.assertEqual(skill.inputs, ["source_docx"])
            self.assertEqual(skill.outputs, ["normalized_docx"])
            self.assertEqual(skill.allowed_tools, ["docx_format_normalizer"])
            self.assertEqual(skill.examples, ["帮我调整 draft.docx 的格式"])


if __name__ == "__main__":
    unittest.main()
