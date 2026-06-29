from datetime import datetime

from yc_agents.analytics.store import AnalyticsStore


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


class AnalyticsRecorder:
    def __init__(self, config, session_id=None):
        self.config = config
        self.session_id = session_id
        self.store = AnalyticsStore(config)

    @property
    def enabled(self):
        return bool(self.config.analytics_enabled)

    @property
    def strict(self):
        return bool(self.config.strict)

    def start_run(self, context):
        if not self.enabled:
            return NullRunAnalytics()

        try:
            self.store.initialize()
            self.store.insert_run(
                run_id=context.run_id,
                workspace_path=str(self.config.workspace_path),
                session_id=self.session_id,
                user_input=context.user_input,
                created_at=context.created_at,
            )
            return RunAnalytics(self, context.run_id)
        except Exception:
            if self.strict:
                raise
            return NullRunAnalytics()

    def record_eval_result(self, result):
        if not self.enabled:
            return None

        try:
            self.store.initialize()
            self.store.insert_eval_result(result)
        except Exception:
            if self.strict:
                raise
        return None

    def close(self):
        return None


class NullRunAnalytics:
    strict = False

    def record_event(self, event):
        return None

    def record_verification(self, verification):
        return None

    def record_final_output(self, output):
        return None

    def finish(self, status, finished_at=None, error_type=None, error_message=None):
        return None


class RunAnalytics:
    def __init__(self, recorder, run_id):
        self.recorder = recorder
        self.run_id = run_id
        self.tool_call_count = 0

    @property
    def strict(self):
        return self.recorder.strict

    def record_event(self, event):
        try:
            event_type = event.get("event_type", "")
            if event_type == "skill_selected":
                selected = (event.get("payload") or {}).get("selected_skill")
                self.recorder.store.update_run(self.run_id, selected_skill=selected)
            if event_type == "tool_called":
                self.tool_call_count += 1
                self.recorder.store.update_run(
                    self.run_id,
                    tool_call_count=self.tool_call_count,
                )
            if event_type.startswith("tool_") or event_type in {
                "effective_allowed_tools",
                "skill_selected",
            }:
                self.recorder.store.insert_trace_event(self.run_id, event)
        except Exception:
            if self.strict:
                raise

    def record_verification(self, verification):
        try:
            self.recorder.store.insert_verification_checks(self.run_id, verification)
            self.recorder.store.update_run(
                self.run_id,
                verification_passed=int(bool((verification or {}).get("passed"))),
            )
        except Exception:
            if self.strict:
                raise

    def record_final_output(self, output):
        try:
            preview = self.recorder.store._preview(output)
            full_text = output if self.recorder.config.full_text else None
            self.recorder.store.update_run(
                self.run_id,
                final_output_preview=preview,
                final_output_full=full_text,
            )
        except Exception:
            if self.strict:
                raise

    def finish(self, status, finished_at=None, error_type=None, error_message=None):
        try:
            fields = {
                "status": status,
                "finished_at": finished_at or _now_iso(),
            }
            if error_type:
                fields["error_type"] = error_type
            if error_message:
                fields["error_message"] = str(error_message)
            self.recorder.store.update_run(self.run_id, **fields)
        except Exception:
            if self.strict:
                raise
