import subprocess

import pytest

from yc_agents.tools.git_inspector import GitInspectorTool


def run(cmd, cwd):
    subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


@pytest.fixture()
def git_repo(tmp_path):
    run(["git", "init"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    run(["git", "add", "app.py"], tmp_path)
    run(["git", "commit", "-m", "initial"], tmp_path)
    return tmp_path


def test_status_returns_structured_branch_and_raw_output(git_repo):
    (git_repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
    tool = GitInspectorTool(git_repo)

    result = tool.run(operation="status")

    assert result["tool"] == "git_inspector"
    assert result["operation"] == "status"
    assert result["ok"] is True
    assert result["branch"]
    assert result["raw_output"]
    assert any(item["path"] == "app.py" for item in result["status"])


def test_diff_worktree_reports_changed_file_summary(git_repo):
    (git_repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
    tool = GitInspectorTool(git_repo)

    result = tool.run(operation="diff_worktree")

    assert result["ok"] is True
    assert result["summary"]["files_changed"] == 1
    assert result["changed_files"][0]["path"] == "app.py"
    assert "diff --git" in result["raw_output"]


def test_diff_staged_reports_staged_change(git_repo):
    (git_repo / "app.py").write_text("print('staged')\n", encoding="utf-8")
    run(["git", "add", "app.py"], git_repo)
    tool = GitInspectorTool(git_repo)

    result = tool.run(operation="diff_staged")

    assert result["ok"] is True
    assert result["changed_files"][0]["path"] == "app.py"


def test_show_commit_returns_commit_metadata(git_repo):
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=git_repo,
        text=True,
    ).strip()
    tool = GitInspectorTool(git_repo)

    result = tool.run(operation="show_commit", ref=commit)

    assert result["ok"] is True
    assert result["commit"] == commit
    assert "initial" in result["raw_output"]


def test_diff_refs_uses_local_refs_without_fetch(git_repo):
    base_ref = subprocess.check_output(
        ["git", "branch", "--show-current"],
        cwd=git_repo,
        text=True,
    ).strip()
    run(["git", "checkout", "-b", "feature"], git_repo)
    (git_repo / "feature.py").write_text("print('feature')\n", encoding="utf-8")
    run(["git", "add", "feature.py"], git_repo)
    run(["git", "commit", "-m", "feature"], git_repo)
    tool = GitInspectorTool(git_repo)

    result = tool.run(operation="diff_refs", base_ref=base_ref, head_ref="HEAD")

    assert result["ok"] is True
    assert result["base_ref"] == base_ref
    assert result["head_ref"] == "HEAD"
    assert any("not fetched" in note.lower() for note in result["notes"])
    assert "feature.py" in result["raw_output"]


def test_blame_rejects_path_traversal(git_repo):
    tool = GitInspectorTool(git_repo)

    with pytest.raises(PermissionError):
        tool.run(operation="blame", file_path="../outside.py")


def test_rejects_unsafe_ref(git_repo):
    tool = GitInspectorTool(git_repo)

    with pytest.raises(ValueError):
        tool.run(operation="show_commit", ref="HEAD;git fetch")


def test_rejects_forbidden_operation(git_repo):
    tool = GitInspectorTool(git_repo)

    with pytest.raises(ValueError):
        tool.run(operation="fetch")
