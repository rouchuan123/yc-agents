import json
from datetime import datetime
from pathlib import Path


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


class StateStore:
    def __init__(self, path):
        self.path = Path(path)
        self.steps_path = self.path.with_name("state-steps.jsonl")

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

    def append_step(self, entry):
        record = dict(entry or {})
        record.setdefault("created_at", _now_iso())
        self.steps_path.parent.mkdir(parents=True, exist_ok=True)

        with self.steps_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

        return record

    def load_steps(self):
        if not self.steps_path.exists():
            return []

        steps = []
        with self.steps_path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    steps.append(json.loads(text))
                except json.JSONDecodeError:
                    # 中断时尾行可能只写了一半：跳过坏行，保留完整步骤。
                    continue
        return steps
