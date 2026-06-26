import pytest

from yc_agents.tools.verification_runner import VerificationRunnerTool


def test_runs_allowed_python_pytest_quiet_command(tmp_path):
    (tmp_path / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    tool = VerificationRunnerTool(tmp_path)

    result = tool.run(command_key="python_pytest_q")

    assert result["tool"] == "verification_runner"
    assert result["command_key"] == "python_pytest_q"
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert "passed" in result["stdout"]


def test_rejects_unknown_or_destructive_command_key(tmp_path):
    tool = VerificationRunnerTool(tmp_path)

    with pytest.raises(ValueError):
        tool.run(command_key="git_push")


def test_heavy_command_requires_explicit_allowance(tmp_path):
    tool = VerificationRunnerTool(tmp_path)

    with pytest.raises(PermissionError):
        tool.run(command_key="npm_build")


def test_heavy_command_can_run_when_explicitly_allowed(tmp_path):
    tool = VerificationRunnerTool(tmp_path)
    result = tool.run(command_key="npm_build", allow_heavy=True)

    assert result["ok"] is False
    assert result["command_key"] == "npm_build"
    assert result["heavy"] is True


def test_rejects_workdir_escape(tmp_path):
    tool = VerificationRunnerTool(tmp_path)

    with pytest.raises(PermissionError):
        tool.run(command_key="python_pytest_q", workdir="../outside")
