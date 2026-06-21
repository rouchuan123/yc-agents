from pathlib import Path


class PathPolicyError(PermissionError):
    pass


class PathPolicy:
    def __init__(self, project_root="."):
        self.project_root = Path(project_root).resolve()

    def validate_write_path(self, file_path):
        path = Path(file_path)

        if path.is_absolute():
            raise PathPolicyError(f"Absolute paths are not allowed: {file_path}")

        if path.name == ".env":
            raise PathPolicyError(".env cannot be written")

        resolved_path = (self.project_root / path).resolve()

        if self.project_root not in resolved_path.parents and resolved_path != self.project_root:
            raise PathPolicyError(f"Path escapes project root: {file_path}")

        return resolved_path