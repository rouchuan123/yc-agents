import subprocess

import pytest

from yc_agents.tools.command_reader import CommandReaderTool


class FakeCompletedProcess:
    def __init__(self, args, returncode=0, stdout="", stderr=""):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def fake_run_factory(calls, stdout="", stderr="", returncode=0):
    def fake_run(command, cwd, check, stdout=None, stderr=None, text=None, timeout=None):
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "check": check,
                "stdout": stdout,
                "stderr": stderr,
                "text": text,
                "timeout": timeout,
            }
        )
        return FakeCompletedProcess(command, returncode=returncode, stdout=stdout_text, stderr=stderr_text)

    stdout_text = stdout
    stderr_text = stderr
    return fake_run


def test_rg_files_returns_structured_files(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run_factory(calls, stdout="src/app.py\ntests/test_app.py\n"),
    )
    tool = CommandReaderTool(tmp_path)

    result = tool.run(command_key="rg_files", path_glob="src/**/*.py")

    assert result["ok"] is True
    assert result["command_key"] == "rg_files"
    assert result["parsed"]["files"] == ["src/app.py", "tests/test_app.py"]
    assert calls[0]["command"] == ["rg", "--files", "-g", "src/**/*.py"]


def test_rg_search_defaults_to_fixed_string(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run_factory(calls, stdout="src/app.py:1:def handler():\n"),
    )
    tool = CommandReaderTool(tmp_path)

    result = tool.run(command_key="rg_search", pattern="def handler()", use_regex=False)

    assert result["ok"] is True
    assert "--fixed-strings" in calls[0]["command"]
    assert result["parsed"]["matches"][0]["path"] == "src/app.py"
    assert result["parsed"]["matches"][0]["line"] == 1


def test_rg_search_can_enable_regex(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run_factory(calls, stdout="src/app.py:1:def handler():\n"),
    )
    tool = CommandReaderTool(tmp_path)

    tool.run(command_key="rg_search", pattern="def .*", use_regex=True)

    assert "--fixed-strings" not in calls[0]["command"]


def test_git_status_short_uses_read_only_git_command(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run_factory(calls, stdout=" M yc_agents/tools/file_reader.py\n"),
    )
    tool = CommandReaderTool(tmp_path)

    result = tool.run(command_key="git_status_short")

    assert result["ok"] is True
    assert calls[0]["command"] == ["git", "status", "--short"]
    assert result["parsed"]["status_lines"] == [" M yc_agents/tools/file_reader.py"]


def test_git_diff_file_rejects_path_traversal(tmp_path):
    tool = CommandReaderTool(tmp_path)

    with pytest.raises(PermissionError):
        tool.run(command_key="git_diff_file", file_path="../outside.py")


def test_git_diff_file_uses_pathspec_separator(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run_factory(calls, stdout="diff --git a/src/app.py b/src/app.py\n"),
    )
    tool = CommandReaderTool(tmp_path)

    result = tool.run(command_key="git_diff_file", file_path="src/app.py")

    assert result["ok"] is True
    assert calls[0]["command"] == ["git", "diff", "--", "src/app.py"]


def test_pytest_collect_only_validates_target_inside_workspace(tmp_path, monkeypatch):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run_factory(calls, stdout="collected 1 item\n"),
    )
    tool = CommandReaderTool(tmp_path)

    result = tool.run(command_key="pytest_collect_only", target="tests/test_app.py")

    assert result["ok"] is True
    assert calls[0]["command"] == ["python", "-m", "pytest", "--collect-only", "tests/test_app.py"]
    assert result["parsed"]["output_lines"] == ["collected 1 item"]


def test_unknown_command_key_is_rejected(tmp_path):
    tool = CommandReaderTool(tmp_path)

    with pytest.raises(ValueError):
        tool.run(command_key="rm_rf")
