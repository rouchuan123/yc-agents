import sqlite3

from yc_agents.analytics.config import AnalyticsConfig
from yc_agents.analytics.store import AnalyticsStore
from yc_agents.mcp.sqlite_server import SQLiteMCPServer


def make_server(tmp_path):
    config = AnalyticsConfig(
        workspace_path=tmp_path,
        db_path=tmp_path / ".ycore" / "sqlite" / "analytics.sqlite",
    )
    store = AnalyticsStore(config)
    store.initialize()
    with sqlite3.connect(config.db_path) as conn:
        conn.execute(
            """
            INSERT INTO agent_runs(run_id, workspace_path, status, started_at)
            VALUES ('run-1', ?, 'finished', '2026-06-28T10:00:00')
            """,
            (str(tmp_path),),
        )
        conn.commit()
    return SQLiteMCPServer(db_path=config.db_path, max_rows=100)


def test_server_initialize_and_list_tools(tmp_path):
    server = make_server(tmp_path)

    init_response = server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    list_response = server.handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )

    assert init_response["result"]["serverInfo"]["name"] == "ycore-sqlite"
    assert {tool["name"] for tool in list_response["result"]["tools"]} == {
        "sqlite.list_tables",
        "sqlite.describe_table",
        "sqlite.query_readonly",
    }


def test_server_query_readonly_returns_rows(tmp_path):
    server = make_server(tmp_path)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "sqlite.query_readonly",
                "arguments": {"sql": "SELECT run_id, status FROM agent_runs"},
            },
        }
    )

    result = response["result"]
    assert result["ok"] is True
    assert result["rows"] == [{"run_id": "run-1", "status": "finished"}]
    assert result["sql"].endswith("LIMIT 100")


def test_server_rejects_delete(tmp_path):
    server = make_server(tmp_path)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "sqlite.query_readonly",
                "arguments": {"sql": "DELETE FROM agent_runs"},
            },
        }
    )

    assert response["result"]["ok"] is False
    assert response["result"]["error_type"] == "sql_rejected"
