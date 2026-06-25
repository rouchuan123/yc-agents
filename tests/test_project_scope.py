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
