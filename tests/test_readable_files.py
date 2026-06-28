from yc_agents.tools.readable_files import (
    DEFAULT_EXCLUDED_DIRS,
    file_type_for_path,
    is_blocked_readable_file,
    is_readable_document_file,
    is_readable_text_file,
    is_readable_workspace_file,
)


def test_code_and_config_files_are_readable_text():
    for file_name in [
        "app.py",
        "service.java",
        "frontend.tsx",
        "settings.yaml",
        "pyproject.toml",
        "pom.xml",
        "Dockerfile",
        "Makefile",
        ".gitignore",
        ".dockerignore",
        ".env.example",
    ]:
        assert is_readable_text_file(file_name), file_name
        assert is_readable_workspace_file(file_name), file_name


def test_documents_are_readable_but_not_text():
    assert is_readable_document_file("notes.docx")
    assert is_readable_document_file("manual.pdf")
    assert is_readable_workspace_file("manual.pdf")
    assert not is_readable_text_file("manual.pdf")


def test_env_file_is_blocked():
    assert is_blocked_readable_file(".env")
    assert not is_readable_text_file(".env")
    assert not is_readable_workspace_file(".env")
    assert is_readable_text_file(".env.example")


def test_file_type_for_special_names():
    assert file_type_for_path("Dockerfile") == "Dockerfile"
    assert file_type_for_path(".env.example") == "env.example"
    assert file_type_for_path("src/app.py") == "py"


def test_default_excluded_dirs_include_heavy_and_private_dirs():
    for dirname in [".ycore", ".git", "node_modules", "venv", "dist", "build", "target"]:
        assert dirname in DEFAULT_EXCLUDED_DIRS
