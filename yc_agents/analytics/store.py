import json
import sqlite3
from datetime import datetime

from yc_agents.analytics.schema import initialize_schema


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


class AnalyticsStore:
    def __init__(self, config):
        self.config = config

    def initialize(self):
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            initialize_schema(conn)

    def connect(self):
        return sqlite3.connect(self.config.db_path)

    def fetchone(self, sql, parameters=()):
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(sql, parameters).fetchone()
            if row is None:
                return None
            return dict(row)

    def insert_run(self, run_id, workspace_path, session_id, user_input, created_at):
        preview = self._preview(user_input)
        full_text = user_input if self.config.full_text else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_runs(
                    run_id, workspace_path, session_id, user_input_preview,
                    user_input_full, status, started_at
                )
                VALUES (?, ?, ?, ?, ?, 'running', ?)
                """,
                (run_id, workspace_path, session_id, preview, full_text, created_at),
            )
            conn.commit()

    def update_run(self, run_id, **fields):
        if not fields:
            return

        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = list(fields.values())
        values.append(run_id)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE agent_runs SET {assignments} WHERE run_id = ?",
                values,
            )
            conn.commit()

    def insert_trace_event(self, run_id, event):
        payload = event.get("payload", {}) or {}
        tool_name = payload.get("tool_name") or payload.get("name")
        ok = payload.get("ok")
        if ok is None and event.get("event_type") == "tool_called":
            ok = True
        elif ok is None and event.get("event_type", "").startswith("tool_"):
            ok = (
                False
                if event.get("event_type")
                in {"tool_failed", "tool_denied", "tool_validation_failed"}
                else None
            )

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO trace_events(
                    run_id, event_type, tool_name, ok, error_type,
                    payload_preview, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event.get("event_type", ""),
                    tool_name,
                    None if ok is None else int(bool(ok)),
                    payload.get("error_type"),
                    self._preview(json.dumps(payload, ensure_ascii=False)),
                    event.get("created_at") or _now_iso(),
                ),
            )
            conn.commit()

    def insert_verification_checks(self, run_id, verification):
        checks = list((verification or {}).get("checks") or [])
        with self.connect() as conn:
            for check in checks:
                conn.execute(
                    """
                    INSERT INTO verification_checks(
                        run_id, check_name, passed, message, created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        check.get("name", ""),
                        int(bool(check.get("passed"))),
                        check.get("message", ""),
                        _now_iso(),
                    ),
                )
            conn.commit()

    def insert_eval_result(self, result):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO eval_results(
                    case_id, category, run_id, keyword_success, tool_success,
                    forbidden_tool_success, trace_event_success, retrieval_hit,
                    noise_resistance_score, noise_resistance_success,
                    conflict_awareness_success, latency_seconds, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.get("case_id", ""),
                    result.get("category", ""),
                    result.get("run_id"),
                    int(bool(result.get("keyword_success"))),
                    int(bool(result.get("tool_success"))),
                    int(bool(result.get("forbidden_tool_success"))),
                    int(bool(result.get("trace_event_success"))),
                    int(bool(result.get("retrieval_hit"))),
                    float(result.get("noise_resistance_score", 0)),
                    int(bool(result.get("noise_resistance_success"))),
                    int(bool(result.get("conflict_awareness_success"))),
                    float(result.get("latency_seconds", 0)),
                    _now_iso(),
                ),
            )
            conn.commit()

    def _preview(self, text):
        text = str(text or "")
        return text[: self.config.preview_chars]
