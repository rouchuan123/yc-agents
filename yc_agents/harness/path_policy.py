from pathlib import Path


class PathPolicyError(PermissionError):
    pass


PROTECTED_FILE_NAMES = {
    ".env",
    "requirements.txt",
    "pyproject.toml",
    "main.py",
}


class PathPolicy:
    def __init__(self, project_root=".", protected_file_names=None):
        self.project_root = Path(project_root).resolve()
        self.protected_file_names = set(
            protected_file_names or PROTECTED_FILE_NAMES
        )

    def validate_write_path(self, file_path, allow_overwrite=False):
        path = Path(file_path)

        if path.is_absolute():
            raise PathPolicyError(f"Absolute paths are not allowed: {file_path}")

        if ".env" in path.parts:
            raise PathPolicyError(".env cannot be written")

        resolved_path = (self.project_root / path).resolve()

        if self.project_root not in resolved_path.parents and resolved_path != self.project_root:
            raise PathPolicyError(f"Path escapes project root: {file_path}")

        if (
            resolved_path.exists()
            and path.name in self.protected_file_names
            and not allow_overwrite
        ):
            raise PathPolicyError(
                f"Protected file overwrite requires approval: {file_path}"
            )

        return resolved_path
