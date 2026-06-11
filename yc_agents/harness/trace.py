import json
from datetime import datetime


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


class TraceRecorder:
    def __init__(self, context):
        self.context = context
        self.events = []

    def record(self, event_type, payload=None):
        event = {
            "event_type": event_type,
            "created_at": _now_iso(),
            "payload": payload or {},
        }
        self.events.append(event)

    def save(self):
        self.context.outputs_dir.mkdir(parents=True, exist_ok=True)
        trace_path = self.context.outputs_dir / "trace.json"

        trace_data = {
            "run_id": self.context.run_id,
            "created_at": self.context.created_at,
            "user_input": self.context.user_input,
            "events": self.events,
        }

        with trace_path.open("w", encoding="utf-8") as f:
            json.dump(trace_data, f, ensure_ascii=False, indent=2)

        return trace_path