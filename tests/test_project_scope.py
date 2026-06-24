from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_only_document_format_normalizer_skill_is_shipped():
    skill_dirs = [
        path.name
        for path in (ROOT / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    ]

    assert skill_dirs == ["document-format-normalizer"]


def test_desktop_application_is_removed():
    assert not (ROOT / "desktop").exists()
    assert not (ROOT / "yc_agents" / "desktop").exists()


def test_readme_positions_first_landing_as_document_format_normalization():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "首个落地点：Word 文档格式调整" in readme
    assert "桌面端" not in readme
    assert "Electron" not in readme


def test_test_script_is_python_only():
    script = (ROOT / "scripts" / "test.ps1").read_text(encoding="utf-8")

    assert "python -m pytest -q" in script
    assert "desktop" not in script.lower()
    assert "npm" not in script.lower()
