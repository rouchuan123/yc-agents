import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        self.sessions_dir = self.project_root / "sessions"

    def create(self, title):
        session = {
            "id": f"session_{uuid.uuid4().hex[:12]}",
            "title": title,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "messages": [],
            "run_ids": [],
        }
        self._save(session)
        return session

    def list(self):
        if not self.sessions_dir.exists():
            return []
        return [
            self._load(path.stem)
            for path in sorted(self.sessions_dir.glob("*.json"))
        ]

    def get(self, session_id):
        return self._load(session_id)

    def append_message(self, session_id, role, content):
        session = self._load(session_id)
        session["messages"].append(
            {
                "role": role,
                "content": content,
                "created_at": utc_now_iso(),
            }
        )
        session["updated_at"] = utc_now_iso()
        self._save(session)
        return session

    def link_run(self, session_id, run_id):
        session = self._load(session_id)
        if run_id not in session["run_ids"]:
            session["run_ids"].append(run_id)
        session["updated_at"] = utc_now_iso()
        self._save(session)
        return session

    def _path(self, session_id):
        return self.sessions_dir / f"{session_id}.json"

    def _load(self, session_id):
        with self._path(session_id).open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, session):
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        with self._path(session["id"]).open("w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
