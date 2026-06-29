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

    assert version == "1"
    assert journal_mode.lower() == "wal"
    assert {
        "agent_runs",
        "trace_events",
        "verification_checks",
        "eval_results",
    } <= tables


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
