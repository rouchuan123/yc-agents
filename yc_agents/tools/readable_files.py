from pathlib import Path


TEXT_READABLE_SUFFIXES = {
    ".md",
    ".txt",
    ".py",
    ".pyi",
    ".ipynb",
    ".toml",
    ".ini",
    ".cfg",
    ".java",
    ".xml",
    ".properties",
    ".gradle",
    ".kt",
    ".kts",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".svelte",
    ".json",
    ".mjs",
    ".cjs",
    ".html",
    ".css",
    ".scss",
    ".less",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".yml",
    ".yaml",
    ".sql",
    ".sh",
    ".ps1",
    ".bat",
}

DOCUMENT_READABLE_SUFFIXES = {".docx", ".pdf"}

READABLE_SPECIAL_NAMES = {
    "Dockerfile",
    "Makefile",
    "README",
    "LICENSE",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "pom.xml",
    ".dockerignore",
    ".gitignore",
    ".env.example",
}

BLOCKED_FILE_NAMES = {".env"}

DEFAULT_EXCLUDED_DIRS = {
    ".ycore",
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "target",
    "coverage",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
}


def normalized_name(path):
    return Path(path).name


def is_blocked_readable_file(path):
    return normalized_name(path) in BLOCKED_FILE_NAMES


def is_readable_text_file(path):
    path = Path(path)
    if is_blocked_readable_file(path):
        return False
    return path.suffix.lower() in TEXT_READABLE_SUFFIXES or path.name in READABLE_SPECIAL_NAMES


def is_readable_document_file(path):
    path = Path(path)
    if is_blocked_readable_file(path):
        return False
    return path.suffix.lower() in DOCUMENT_READABLE_SUFFIXES


def is_readable_workspace_file(path):
    return is_readable_text_file(path) or is_readable_document_file(path)


def file_type_for_path(path):
    path = Path(path)
    if path.name in READABLE_SPECIAL_NAMES and not path.suffix:
        return path.name
    if path.name == ".env.example":
        return "env.example"
    return path.suffix.lower().lstrip(".")
