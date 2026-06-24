from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_uses_ycore_name():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "ycore"
    assert "YCore" in pyproject["project"]["description"]


def test_readme_presents_ycore_as_project_name():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert readme.startswith("# YCore")
    assert "`YCore`" in readme


def test_user_facing_runtime_text_uses_ycore_brand():
    user_facing_paths = [
        ROOT / "yc_agents" / "agents" / "skill_agent.py",
        ROOT / "yc_agents" / "agents" / "skill_runtime_agent.py",
        ROOT / "yc_agents" / "intent" / "llm_classifier.py",
        ROOT / "yc_agents" / "harness" / "enhanced_demo.py",
    ]

    for path in user_facing_paths:
        text = path.read_text(encoding="utf-8")
        assert "YC Agents" not in text
        assert "yc-agents" not in text
