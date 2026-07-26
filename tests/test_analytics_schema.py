import sqlite3

from yc_agents.analytics.config import AnalyticsConfig
from yc_agents.analytics.store import AnalyticsStore


def test_store_initializes_schema_version_and_wal(tmp_path):
    config = AnalyticsConfig(
        workspace_path=tmp_path,
        db_path=tmp_path / ".ycore" / "sqlite" / "analytics.sqlite",
    )
    store = AnalyticsStore(config)

    store.initialize()

    with sqlite3.connect(config.db_path) as conn:
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert version == "2"
    assert journal_mode.lower() == "wal"
    assert {
        "agent_runs",
        "trace_events",
        "verification_checks",
        "eval_results",
    } <= tables


def test_store_creates_agent_run_token_columns(tmp_path):
    config = AnalyticsConfig(
        workspace_path=tmp_path,
        db_path=tmp_path / ".ycore" / "sqlite" / "analytics.sqlite",
    )
    store = AnalyticsStore(config)

    store.initialize()

    with sqlite3.connect(config.db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(agent_runs)")
        }

    assert {
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "total_tokens",
    } <= columns


def test_initialize_migrates_legacy_agent_runs_without_token_columns(tmp_path):
    db_path = tmp_path / ".ycore" / "sqlite" / "analytics.sqlite"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE agent_runs (
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
            """
        )
        conn.execute(
            """
            INSERT INTO agent_runs(run_id, workspace_path, status, started_at)
            VALUES ('legacy-run', 'ws', 'finished', '2026-06-28T10:00:00')
            """
        )
        conn.commit()

    config = AnalyticsConfig(workspace_path=tmp_path, db_path=db_path)
    store = AnalyticsStore(config)
    store.initialize()
    store.update_run("legacy-run", total_tokens=321, input_tokens=200)

    row = store.fetchone(
        """
        SELECT status, input_tokens, output_tokens, cached_tokens, total_tokens
        FROM agent_runs WHERE run_id = 'legacy-run'
        """
    )

    assert row == {
        "status": "finished",
        "input_tokens": 200,
        "output_tokens": None,
        "cached_tokens": None,
        "total_tokens": 321,
    }


def test_store_inserts_and_updates_agent_run(tmp_path):
    config = AnalyticsConfig(
        workspace_path=tmp_path,
        db_path=tmp_path / ".ycore" / "sqlite" / "analytics.sqlite",
    )
    store = AnalyticsStore(config)
    store.initialize()

    store.insert_run(
        run_id="run-1",
        workspace_path=str(tmp_path),
        session_id="session-1",
        user_input="hello world",
        created_at="2026-06-28T10:00:00",
    )
    store.update_run("run-1", status="finished", selected_skill="code-review")

    row = store.fetchone(
        "SELECT status, selected_skill FROM agent_runs WHERE run_id = ?",
        ("run-1",),
    )

    assert row == {"status": "finished", "selected_skill": "code-review"}
