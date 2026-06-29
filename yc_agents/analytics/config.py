from dataclasses import dataclass
from pathlib import Path


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
    def from_ycore(cls, workspace_path, data):
        workspace_path = Path(workspace_path)
        data = data or {}
        db_override = str(data.get("dbPath") or "").strip()
        db_path = (
            Path(db_override)
            if db_override
            else workspace_path / ".ycore" / "sqlite" / "analytics.sqlite"
        )

        sqlite_mcp = data.get("sqliteMcp") or {}
        return cls(
            workspace_path=workspace_path,
            db_path=db_path,
            analytics_enabled=bool(data.get("enabled", False)),
            sqlite_mcp_enabled=bool(sqlite_mcp.get("enabled", False)),
            full_text=bool(data.get("fullText", False)),
            strict=bool(data.get("strict", False)),
            preview_chars=int(data.get("previewChars", 200)),
            max_rows=int(data.get("maxRows", 100)),
            retention_runs=int(data.get("retentionRuns", 1000)),
        )
