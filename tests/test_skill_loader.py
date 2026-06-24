import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yc_agents.skills.loader import SkillLoader


class TestSkillLoader(unittest.TestCase):
    def test_load_all_reads_opening_report_skill(self):
        loader = SkillLoader("skills")

        skills = loader.load_all()

        self.assertGreaterEqual(len(skills), 1)

        opening_report = next(
            skill for skill in skills if skill.name == "opening-report"
        )

        self.assertTrue(opening_report.description)
        self.assertEqual(
            opening_report.allowed_tools,
            [
                "docx_reader",
                "file_reader",
                "workspace_files",
                "rag_search",
                "markdown_writer",
            ],
        )
        self.assertIn("开题报告 Skill", opening_report.body)
        self.assertEqual(opening_report.path, "skills/opening-report")
    
    def test_load_all_discovers_skill_related_files(self):
        loader = SkillLoader("skills")

        skills = loader.load_all()

        opening_report = next(
            skill for skill in skills if skill.name == "opening-report"
        )

        self.assertIsInstance(opening_report.scripts, list)
        self.assertIsInstance(opening_report.assets, list)
        self.assertIsInstance(opening_report.references, list)

    def test_load_all_reads_document_format_normalizer_skill(self):
        loader = SkillLoader("skills")

        skills = loader.load_all()

        skill = next(
            skill for skill in skills if skill.name == "document-format-normalizer"
        )
        self.assertIn("docx_format_normalizer", skill.allowed_tools)
        self.assertIn("Word", skill.description)
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
            any(
                path.endswith("scripts/docx_format/cli.py")
                for path in [script["path"] for script in skill.scripts]
            )
        )

    def test_load_one_reads_expanded_metadata(self):
        with TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "literature-review"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: literature-review",
                        "description: Generate literature review",
                        "triggers:",
                        "  - 文献综述",
                        "  - related work",
                        "inputs:",
                        "  - topic",
                        "outputs:",
                        "  - markdown",
                        "allowed_tools:",
                        "  - rag_search",
                        "examples:",
                        "  - 帮我写多智能体方向文献综述",
                        "---",
                        "",
                        "# Literature Review",
                    ]
                ),
                encoding="utf-8",
            )

            skill = SkillLoader(tmpdir).load_one(skill_dir)

            self.assertEqual(skill.triggers, ["文献综述", "related work"])
            self.assertEqual(skill.inputs, ["topic"])
            self.assertEqual(skill.outputs, ["markdown"])
            self.assertEqual(skill.allowed_tools, ["rag_search"])
            self.assertEqual(skill.examples, ["帮我写多智能体方向文献综述"])


if __name__ == "__main__":
    unittest.main()
