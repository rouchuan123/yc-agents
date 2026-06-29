import os
from dataclasses import dataclass
from pathlib import Path


def parse_bool_env(name, value):
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{name} must be true or false, got {value!r}")


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return parse_bool_env(name, value)


def _env_int(name, default):
    value = os.environ.get(name)
    if value is None or value == "":
        return default

    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


@dataclass(frozen=True)
class AnalyticsConfig:
    workspace_path: Path
    db_path: Path
    analytics_enabled: bool = False
    sqlite_mcp_enabled: bool = False
    full_text: bool = False
    strict: bool = False
    preview_chars: int = 200
    max_rows: int = 100
    retention_runs: int = 1000

    @classmethod
    def from_env(cls, workspace_path):
        workspace_path = Path(workspace_path)
        db_override = os.environ.get("YCORE_ANALYTICS_DB_PATH", "").strip()
        db_path = (
            Path(db_override)
            if db_override
            else workspace_path / ".ycore" / "sqlite" / "analytics.sqlite"
        )

        return cls(
            workspace_path=workspace_path,
            db_path=db_path,
            analytics_enabled=_env_bool("YCORE_ANALYTICS_ENABLED", False),
            sqlite_mcp_enabled=_env_bool("YCORE_SQLITE_MCP_ENABLED", False),
            full_text=_env_bool("YCORE_ANALYTICS_FULL_TEXT", False),
            strict=_env_bool("YCORE_ANALYTICS_STRICT", False),
            preview_chars=_env_int("YCORE_ANALYTICS_PREVIEW_CHARS", 200),
            max_rows=_env_int("YCORE_ANALYTICS_MAX_ROWS", 100),
            retention_runs=_env_int("YCORE_ANALYTICS_RETENTION_RUNS", 1000),
        )
