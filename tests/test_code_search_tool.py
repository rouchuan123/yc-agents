import pytest

from yc_agents.tools.code_search import CodeSearchTool


@pytest.fixture()
def workspace(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "def handler():\n    return 'ok'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "from src.app import handler\n",
        encoding="utf-8",
    )
    return tmp_path


def test_list_files_returns_workspace_relative_paths(workspace):
    tool = CodeSearchTool(workspace)

    result = tool.run(operation="list_files")

    assert result["tool"] == "code_search"
    assert result["operation"] == "list_files"
    assert result["ok"] is True
    assert "src/app.py" in result["files"]
    assert "tests/test_app.py" in result["files"]


def test_search_returns_matches_with_context(workspace):
    tool = CodeSearchTool(workspace)

    result = tool.run(operation="search", pattern="handler", context_lines=1)

    assert result["ok"] is True
    assert result["count"] >= 2
    assert any(
        match["path"] == "src/app.py" and match["line"] == 1
        for match in result["matches"]
    )
    assert result["raw_output"]


def test_snippet_returns_bounded_lines(workspace):
    tool = CodeSearchTool(workspace)

    result = tool.run(operation="snippet", file_path="src/app.py", line=2, context_lines=1)

    assert result["ok"] is True
    assert result["path"] == "src/app.py"
    assert [row["line"] for row in result["lines"]] == [1, 2]


def test_rejects_path_traversal(workspace):
    tool = CodeSearchTool(workspace)

    with pytest.raises(PermissionError):
        tool.run(operation="snippet", file_path="../outside.py", line=1)
