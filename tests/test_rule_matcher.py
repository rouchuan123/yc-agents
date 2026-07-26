import unittest
from pathlib import Path

from yc_agents.intent.rule_matcher import RuleIntentMatcher
from yc_agents.skills.definition import SkillDefinition
from yc_agents.skills.loader import SkillLoader


class TestRuleIntentMatcher(unittest.TestCase):
    def test_match_code_review_by_keywords(self):
        skills = [
            SkillDefinition(
                name="code-review",
                description="Project architecture and risk review",
                allowed_tools=[],
                body="",
                path="skills/code-review",
            )
        ]

        matches = RuleIntentMatcher().match(
            "please review this project architecture and risks",
            skills,
        )

        self.assertEqual(matches[0]["skill_name"], "code-review")
        self.assertGreater(matches[0]["confidence"], 0)
        self.assertIn("review", matches[0]["matched_keywords"])
        self.assertIn("architecture", matches[0]["matched_keywords"])

    def test_generic_document_frontmatter_triggers_match_with_high_confidence(self):
        skills = [
            SkillDefinition(
                name="docx-template-authoring",
                description="Word 模板仿写",
                allowed_tools=[],
                body="",
                path="skills/docx-template-authoring",
                triggers=["文档", "Word", "DOCX", "文档模板"],
            )
        ]

        matches = RuleIntentMatcher().match(
            "帮我根据工作区模板生成文档",
            skills,
        )

        self.assertEqual(matches[0]["skill_name"], "docx-template-authoring")
        self.assertGreaterEqual(matches[0]["confidence"], 0.9)
        self.assertIn("文档", matches[0]["matched_keywords"])

    def test_docx_skill_frontmatter_uses_only_generic_document_triggers(self):
        project_root = Path(__file__).resolve().parents[1]
        skill = SkillLoader(
            project_root / "skills",
            enabled_skills={"docx-template-authoring"},
        ).load_all()[0]

        self.assertTrue(
            {
                "文档",
                "生成文档",
                "写文档",
                "Word",
                "Word文档",
                "DOCX",
                "导出Word",
                "文档模板",
                "沿用排版",
                "沿用格式",
            }.issubset(set(skill.triggers))
        )
        self.assertTrue({"文献综述", "论文", "报告"}.isdisjoint(skill.triggers))

    def test_business_topic_without_document_word_does_not_rule_match(self):
        skill = SkillDefinition(
            name="docx-template-authoring",
            description="Word 模板仿写",
            body="",
            path="skills/docx-template-authoring",
            triggers=["文档", "Word", "DOCX"],
        )

        matches = RuleIntentMatcher().match("写一篇文献综述、论文或报告", [skill])

        self.assertEqual(matches, [])

    def test_explicit_markdown_document_does_not_select_docx_skill(self):
        skill = SkillDefinition(
            name="docx-template-authoring",
            description="Word 模板仿写",
            body="",
            path="skills/docx-template-authoring",
            triggers=["文档", "Word", "DOCX"],
        )

        matches = RuleIntentMatcher().match("帮我写 Markdown 文档", [skill])

        self.assertEqual(matches, [])

    def test_match_returns_empty_list_when_no_keywords_match(self):
        skills = [
            SkillDefinition(
                name="code-review",
                description="Project architecture and risk review",
                allowed_tools=[],
                body="",
                path="skills/code-review",
            )
        ]

        matches = RuleIntentMatcher().match("how is the weather today?", skills)

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
