import argparse
import json
import sqlite3
import sys
from pathlib import Path

from yc_agents.analytics.config import AnalyticsConfig
from yc_agents.analytics.store import AnalyticsStore
from yc_agents.mcp.sqlite_security import SQLSecurityError, normalize_readonly_sql


class SQLiteMCPServer:
    def __init__(self, db_path, max_rows=100):
        self.db_path = Path(db_path)
        self.max_rows = int(max_rows)

    def handle_request(self, request):
        method = request.get("method")
        request_id = request.get("id")
        try:
            if method == "initialize":
                return self._response(request_id, self._initialize_result())
            if method == "tools/list":
                return self._response(request_id, {"tools": self._tools()})
            if method == "tools/call":
                params = request.get("params") or {}
                return self._response(
                    request_id,
                    self.call_tool(params.get("name"), params.get("arguments") or {}),
                )
            return self._error(request_id, -32601, f"Unknown method: {method}")
        except Exception as exc:
            return self._error(request_id, -32000, str(exc))

    def call_tool(self, name, arguments):
        if name == "sqlite.list_tables":
            return self._list_tables()
        if name == "sqlite.describe_table":
            return self._describe_table(arguments.get("table", ""))
        if name == "sqlite.query_readonly":
            return self._query_readonly(arguments.get("sql", ""))
        return {
            "ok": False,
            "error_type": "unknown_tool",
            "error": f"Unknown tool: {name}",
        }

    def _initialize_result(self):
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ycore-sqlite", "version": "0.1.0"},
        }

    def _tools(self):
        return [
            {
                "name": "sqlite.list_tables",
                "description": "List analytics SQLite tables.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "sqlite.describe_table",
                "description": "Describe one analytics SQLite table.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"table": {"type": "string"}},
                    "required": ["table"],
                },
            },
            {
                "name": "sqlite.query_readonly",
                "description": "Run one read-only SELECT query.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"sql": {"type": "string"}},
                    "required": ["sql"],
                },
            },
        ]

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _list_tables(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        return {"ok": True, "tables": [row[0] for row in rows]}

    def _describe_table(self, table):
        with self._connect() as conn:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {
            "ok": True,
            "table": table,
            "columns": [
                {"name": row[1], "type": row[2], "notnull": bool(row[3])}
                for row in rows
            ],
        }

    def _query_readonly(self, sql):
        try:
            safe_sql = normalize_readonly_sql(sql, max_rows=self.max_rows)
        except SQLSecurityError as exc:
            return {"ok": False, "error_type": "sql_rejected", "error": str(exc)}

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(safe_sql).fetchmany(self.max_rows)
        return {"ok": True, "sql": safe_sql, "rows": [dict(row) for row in rows]}

    def _response(self, request_id, result):
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _error(self, request_id, code, message):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }


def serve_stdio(server, stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        response = server.handle_request(json.loads(line))
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--max-rows", type=int, default=100)
    args = parser.parse_args(argv)

    config = AnalyticsConfig(
        workspace_path=Path(args.workspace),
        db_path=Path(args.db),
        max_rows=args.max_rows,
    )
    AnalyticsStore(config).initialize()
    serve_stdio(SQLiteMCPServer(args.db, max_rows=args.max_rows))


if __name__ == "__main__":
    main()
