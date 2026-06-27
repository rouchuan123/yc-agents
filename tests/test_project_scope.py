from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_two_chinese_business_skills_are_shipped_by_default():
    skill_dirs = [
        path.name
        for path in (ROOT / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    ]

    assert skill_dirs == ["code-review", "eval-writer"]


def test_desktop_application_is_removed():
    assert not (ROOT / "desktop").exists()
    assert not (ROOT / "yc_agents" / "desktop").exists()


def test_readme_positions_ycore_as_generic_skill_runtime():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "面向中文用户" in readme
    assert "默认发布两个示例业务 Skill" in readme
    assert "桌面端" not in readme
    assert "Electron" not in readme


def test_project_instruction_template_is_chinese():
    ycore = (ROOT / "YCORE.md").read_text(encoding="utf-8")

    assert "YCore 项目指令" in ycore
    assert "面向中文用户" in ycore
    assert "Do not assume" not in ycore


def test_test_script_is_python_only():
    script = (ROOT / "scripts" / "test.ps1").read_text(encoding="utf-8")

    assert "python -m pytest -q" in script
    assert "desktop" not in script.lower()
    assert "npm" not in script.lower()


def test_readme_positions_ycore_as_generic_skill_driven_harness():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "通用的 skill-driven 本地 Agent Harness" in readme
    assert "具体落地方向由 Skill 决定" in readme
    assert "第一批验证 Skill" in readme
    assert "code-review" in readme
    assert "eval-writer" in readme
    assert ("面向 code" + " agent 的本地 Agent Harness") not in readme
    assert ("code-agent" + " 定位") not in readme
    assert ("论文" + "助手") not in readme
    assert ("文献" + "综述") not in readme
    assert ("开题" + "报告") not in readme
    assert "DOCX 处理包" not in readme


def test_global_docs_keep_ycore_domain_agnostic():
    docs = [
        ROOT / "YCORE.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "docs" / "demo-script.md",
        ROOT / "docs" / "evaluation-report.md",
    ]

    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert "通用" in text, path.relative_to(ROOT)
        assert (
            "由 Skill 决定" in text or "取决于 Skill" in text
        ), path.relative_to(ROOT)
        assert ("面向 code" + " agent 的本地 Agent Harness") not in text, path.relative_to(ROOT)
        assert ("YCore code-agent" + " 定位") not in text, path.relative_to(ROOT)


def test_removed_word_formatting_package_but_docx_reading_stays():
    removed_package = "docx" + "_format"
    removed_tool = "docx" + "_format" + "_normalizer.py"

    assert not (ROOT / "yc_agents" / removed_package).exists()
    assert not (ROOT / "yc_agents" / "tools" / removed_tool).exists()
    assert (ROOT / "yc_agents" / "tools" / "docx_reader.py").exists()
    assert (ROOT / "yc_agents" / "tools" / "file_reader.py").exists()
