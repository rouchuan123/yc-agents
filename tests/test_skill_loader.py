import unittest

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
                "rag_search",
                "markdown_writer",
            ],
        )
        self.assertIn("开题报告 Skill", opening_report.body)
        self.assertEqual(opening_report.path, "skills/opening-report")


if __name__ == "__main__":
    unittest.main()