import json
from datetime import datetime
from pathlib import Path


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


class StateStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return {
                "current_step": None,
                "status": "not_started",
                "history": [],
            }

        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_checkpoint(self, step, status, details=None):
        state = self.load()
        if hasattr(status, "value"):
            status = status.value

        checkpoint = {
            "step": step,
            "status": status,
            "details": details or {},
            "created_at": _now_iso(),
        }

        state["current_step"] = step
        state["status"] = status
        state["history"].append(checkpoint)

        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self.path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        return state

    def latest_checkpoint(self):
        state = self.load()
        history = state.get("history", [])
        return history[-1] if history else None
