import sqlite3
from dataclasses import dataclass

import pytest

from yc_agents.analytics.config import AnalyticsConfig
from yc_agents.analytics.recorder import AnalyticsRecorder


@dataclass
class FakeContext:
    run_id: str = "run-1"
    user_input: str = "用户输入" * 80
    created_at: str = "2026-06-28T10:00:00"


def test_recorder_starts_run_records_events_and_final_output(tmp_path):
    config = AnalyticsConfig(
        workspace_path=tmp_path,
        db_path=tmp_path / ".ycore" / "sqlite" / "analytics.sqlite",
        analytics_enabled=True,
        preview_chars=20,
    )
    recorder = AnalyticsRecorder(config, session_id="session-1")
    run = recorder.start_run(FakeContext())

    run.record_event(
        {
            "event_type": "tool_called",
            "created_at": "2026-06-28T10:00:01",
            "payload": {"tool_name": "workspace_files", "result": {"ok": True}},
        }
    )
    run.record_verification(
        {
            "passed": True,
            "checks": [
                {"name": "final_output_non_empty", "passed": True, "message": "ok"}
            ],
        }
    )
    run.record_final_output("最终输出" * 80)
    run.finish("finished", finished_at="2026-06-28T10:00:02")

    with sqlite3.connect(config.db_path) as conn:
        run_row = conn.execute(
            """
            SELECT status, tool_call_count, verification_passed,
                   length(user_input_preview), length(final_output_preview)
            FROM agent_runs
            """
        ).fetchone()
        event_row = conn.execute(
            "SELECT event_type, tool_name, ok FROM trace_events"
        ).fetchone()
        check_row = conn.execute(
            "SELECT check_name, passed FROM verification_checks"
        ).fetchone()

    assert run_row == ("finished", 1, 1, 20, 20)
    assert event_row == ("tool_called", "workspace_files", 1)
    assert check_row == ("final_output_non_empty", 1)


def test_recorder_strict_mode_raises_write_errors(tmp_path):
    config = AnalyticsConfig(
        workspace_path=tmp_path,
        db_path=tmp_path / "missing" / "analytics.sqlite",
        analytics_enabled=True,
        strict=True,
    )
    recorder = AnalyticsRecorder(config, session_id="session-1")
    recorder.store.initialize = lambda: (_ for _ in ()).throw(
        RuntimeError("db failed")
    )

    with pytest.raises(RuntimeError, match="db failed"):
        recorder.start_run(FakeContext())
