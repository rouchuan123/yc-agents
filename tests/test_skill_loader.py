import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yc_agents.skills.loader import SkillLoader


class TestSkillLoader(unittest.TestCase):
    def test_load_all_reads_published_chinese_skills(self):
        loader = SkillLoader("skills")

        skills = loader.load_all()

        self.assertEqual([skill.name for skill in skills], ["code-review", "eval-writer"])
        self.assertTrue(all("中文" in skill.body for skill in skills))
        self.assertTrue(all("workspace_files" in skill.allowed_tools for skill in skills))
        self.assertTrue(all("file_reader" in skill.allowed_tools for skill in skills))

    def test_code_review_skill_requires_deep_evidence_based_review(self):
        loader = SkillLoader("skills")

        skill = loader.load_one(Path("skills") / "code-review")

        required_markers = [
            "已读取文件清单",
            "项目地图",
            "关键链路",
            "证据",
            "风险分级",
            "测试缺口",
            "未确认事项",
            "不要提前总结",
        ]
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, skill.body)

    def test_code_review_skill_exposes_project_audit_references(self):
        loader = SkillLoader("skills")

        skill = loader.load_one(Path("skills") / "code-review")

        reference_names = {Path(path).name for path in skill.references}
        expected_references = {
            "architecture-review-guide.md",
            "security-review-guide.md",
            "performance-review-guide.md",
            "code-quality-universal.md",
            "common-bugs-checklist.md",
            "python.md",
            "typescript.md",
            "react.md",
            "go.md",
            "rust.md",
        }
        self.assertTrue(
            expected_references.issubset(reference_names),
            f"Missing references: {sorted(expected_references - reference_names)}",
        )

        asset_names = {Path(path).name for path in skill.assets}
        self.assertIn("project-audit-checklist.md", asset_names)
        self.assertIn("project-audit-report-template.md", asset_names)
        self.assertFalse(
            any("pr-analyzer" in script["path"] for script in skill.scripts),
            "Project audit skill should not migrate the PR diff analyzer script.",
        )

        required_markers = [
            "本地项目体检",
            "不是 PR diff 审查",
            "按需读取参考资料",
            "横向审查指南",
            "语言与框架指南",
            "已确认事实",
            "基于代码的推断",
            "未确认事项",
        ]
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, skill.body)

    def test_code_review_skill_allows_review_evidence_tools(self):
        loader = SkillLoader("skills")

        skill = loader.load_one(Path("skills") / "code-review")

        for tool_name in ["git_inspector", "code_search", "verification_runner"]:
            with self.subTest(tool_name=tool_name):
                self.assertIn(tool_name, skill.allowed_tools)

        required_markers = [
            "项目体检模式",
            "变更/PR 审查模式",
            "git_inspector",
            "code_search",
            "verification_runner",
            "不自动 fetch",
            "重型验证",
        ]
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, skill.body)

    def test_load_one_reads_expanded_metadata(self):
        with TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "code-review"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: code-review",
                        "description: 审查项目结构",
                        "triggers:",
                        "  - 代码审查",
                        "  - 架构总结",
                        "inputs:",
                        "  - project_files",
                        "outputs:",
                        "  - review_note",
                        "allowed_tools:",
                        "  - workspace_files",
                        "  - file_reader",
                        "examples:",
                        "  - 帮我审查这个项目",
                        "---",
                        "",
                        "# 代码审查",
                    ]
                ),
                encoding="utf-8",
            )

            skill = SkillLoader(tmpdir).load_one(skill_dir)

            self.assertEqual(skill.triggers, ["代码审查", "架构总结"])
            self.assertEqual(skill.inputs, ["project_files"])
            self.assertEqual(skill.outputs, ["review_note"])
            self.assertEqual(skill.allowed_tools, ["workspace_files", "file_reader"])
            self.assertEqual(skill.examples, ["帮我审查这个项目"])


if __name__ == "__main__":
    unittest.main()
