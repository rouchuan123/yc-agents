import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        self.runs_dir = self.project_root / "runs"

    def create(self, session_id, user_input):
        run = {
            "id": f"run_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "status": "running",
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "user_input": user_input,
        }
        run_dir = self._run_dir(run["id"])
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "input.md").write_text(user_input, encoding="utf-8")
        self._write_json(run["id"], "run.json", run)
        self._write_json(run["id"], "trace.json", {"events": []})
        return run

    def list(self):
        if not self.runs_dir.exists():
            return []
        return [
            self.get(path.name)
            for path in sorted(self.runs_dir.iterdir())
            if path.is_dir()
        ]

    def get(self, run_id):
        with (self._run_dir(run_id) / "run.json").open("r", encoding="utf-8") as f:
            return json.load(f)

    def append_event(self, run_id, event_type, payload=None):
        payload = payload or {}
        trace_path = self._run_dir(run_id) / "trace.json"
        with trace_path.open("r", encoding="utf-8") as f:
            trace = json.load(f)
        trace["events"].append(
            {
                "event_type": event_type,
                "created_at": utc_now_iso(),
                "payload": payload,
            }
        )
        self._write_json(run_id, "trace.json", trace)
        return trace

    def complete(self, run_id, final_output):
        run = self.get(run_id)
        run["status"] = "completed"
        run["updated_at"] = utc_now_iso()
        (self._run_dir(run_id) / "final_output.md").write_text(
            final_output,
            encoding="utf-8",
        )
        self._write_json(run_id, "run.json", run)
        return run

    def fail(self, run_id, error):
        run = self.get(run_id)
        run["status"] = "failed"
        run["updated_at"] = utc_now_iso()
        run["error"] = error
        self._write_json(run_id, "run.json", run)
        return run

    def cancel(self, run_id):
        run = self.get(run_id)
        run["status"] = "cancelled"
        run["updated_at"] = utc_now_iso()
        self._write_json(run_id, "run.json", run)
        return run

    def read_file(self, run_id, file_name):
        path = (self._run_dir(run_id) / file_name).resolve()
        if not self._is_relative_to(path, self._run_dir(run_id).resolve()):
            raise ValueError(f"Path is outside run directory: {file_name}")
        return path.read_text(encoding="utf-8")

    def _run_dir(self, run_id):
        return self.runs_dir / run_id

    def _write_json(self, run_id, file_name, data):
        path = self._run_dir(run_id) / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _is_relative_to(self, path, parent):
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False
