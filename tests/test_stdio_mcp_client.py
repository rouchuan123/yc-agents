import sqlite3
import sys

from yc_agents.analytics.config import AnalyticsConfig
from yc_agents.analytics.store import AnalyticsStore
from yc_agents.mcp.stdio_client import StdioMCPClient


def test_stdio_client_calls_sqlite_server(tmp_path):
    db_path = tmp_path / ".ycore" / "sqlite" / "analytics.sqlite"
    config = AnalyticsConfig(workspace_path=tmp_path, db_path=db_path)
    AnalyticsStore(config).initialize()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO agent_runs(run_id, workspace_path, status, started_at)
            VALUES ('run-1', ?, 'finished', '2026-06-28T10:00:00')
            """,
            (str(tmp_path),),
        )
        conn.commit()

    client = StdioMCPClient(
        command=[
            sys.executable,
            "-m",
            "yc_agents.mcp.sqlite_server",
            "--db",
            str(db_path),
            "--workspace",
            str(tmp_path),
            "--max-rows",
            "100",
        ],
        server_name="sqlite",
        timeout_seconds=5,
    )
    try:
        client.start()
        tools = client.list_tools()
        result = client.call_tool(
            "sqlite",
            "sqlite.query_readonly",
            {"sql": "SELECT run_id FROM agent_runs"},
        )
    finally:
        client.close()

    assert "sqlite.query_readonly" in {tool["name"] for tool in tools}
    assert result["ok"] is True
    assert result["rows"] == [{"run_id": "run-1"}]
