SCHEMA_VERSION = "1"


SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_runs (
        run_id TEXT PRIMARY KEY,
        workspace_path TEXT NOT NULL,
        session_id TEXT,
        user_input_preview TEXT,
        user_input_full TEXT,
        final_output_preview TEXT,
        final_output_full TEXT,
        selected_skill TEXT,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        latency_ms INTEGER,
        tool_call_count INTEGER NOT NULL DEFAULT 0,
        verification_passed INTEGER,
        error_type TEXT,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trace_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        tool_name TEXT,
        ok INTEGER,
        error_type TEXT,
        payload_preview TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS verification_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        check_name TEXT NOT NULL,
        passed INTEGER NOT NULL,
        message TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS eval_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT NOT NULL,
        category TEXT NOT NULL,
        run_id TEXT,
        keyword_success INTEGER NOT NULL,
        tool_success INTEGER NOT NULL,
        forbidden_tool_success INTEGER NOT NULL,
        trace_event_success INTEGER NOT NULL,
        retrieval_hit INTEGER NOT NULL,
        noise_resistance_score REAL NOT NULL,
        noise_resistance_success INTEGER NOT NULL,
        conflict_awareness_success INTEGER NOT NULL,
        latency_seconds REAL NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_trace_events_run_id ON trace_events(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_eval_results_case_id ON eval_results(case_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_started_at ON agent_runs(started_at)",
]


def initialize_schema(conn):
    conn.execute("PRAGMA journal_mode=WAL")
    for statement in SCHEMA_SQL:
        conn.execute(statement)
    conn.execute(
        """
        INSERT INTO schema_meta(key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (SCHEMA_VERSION,),
    )
    conn.commit()
