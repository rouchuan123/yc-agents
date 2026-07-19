import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _new_session_id():
    timestamp = datetime.now().strftime("%Y%m%d")
    return f"session_{timestamp}_{uuid4().hex[:8]}"


@dataclass(frozen=True)
class CLISession:
    id: str
    title: str
    workspace: object
    path: Path
    messages_path: Path
    summary_path: Path
    profile_path: Path
    usage_path: Path
    runs_path: Path
    updated_at: str
    message_count: int = 0


class CLISessionStore:
    def __init__(self, workspace):
        self.workspace = workspace
        self.sessions_dir = workspace.sessions_dir
        self.runs_dir = workspace.runs_dir
        self.current_session_path = workspace.current_session_path

    def ensure_current_session(self):
        current_id = self._read_current_session_id()
        if current_id:
            try:
                return self.get_session(current_id)
            except FileNotFoundError:
                pass

        sessions = self.list_sessions()
        if sessions:
            selected = sorted(sessions, key=lambda session: session.updated_at, reverse=True)[0]
            self._write_current_session_id(selected.id)
            return selected

        return self.create_session()

    def create_session(self, title=None):
        session_id = _new_session_id()
        title = title or self._next_default_title()
        session_path = self.sessions_dir / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        now = _now_iso()
        metadata = {
            "id": session_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
        }
        self._write_metadata(session_path, metadata)
        self._ensure_files(session_path)
        self._write_current_session_id(session_id)
        return self._session_from_metadata(session_path, metadata)

    def switch_session(self, session_id):
        session = self.get_session(session_id)
        self._write_current_session_id(session.id)
        return session

    def delete_session(self, session_id=None):
        target = self.get_session(session_id or self.ensure_current_session().id)
        if target.path.exists():
            shutil.rmtree(target.path)
        if target.runs_path.exists():
            shutil.rmtree(target.runs_path)
        memory_log = self.workspace.ycore_dir / "memory" / "sessions" / f"{target.id}.md"
        if memory_log.exists():
            memory_log.unlink()

        remaining = self.list_sessions()
        if remaining:
            selected = sorted(remaining, key=lambda session: session.updated_at, reverse=True)[0]
            self._write_current_session_id(selected.id)
            return selected

        self._write_current_session_id("")
        return self.create_session()

    def get_session(self, session_id):
        session_path = self.sessions_dir / session_id
        metadata_path = session_path / "session.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Session does not exist: {session_id}")

        with metadata_path.open("r", encoding="utf-8") as f:
            metadata = json.load(f)

        self._ensure_files(session_path)
        return self._session_from_metadata(session_path, metadata)

    def list_sessions(self):
        if not self.sessions_dir.exists():
            return []

        sessions = []
        for path in sorted(self.sessions_dir.iterdir()):
            metadata_path = path / "session.json"
            if not path.is_dir() or not metadata_path.exists():
                continue
            with metadata_path.open("r", encoding="utf-8") as f:
                metadata = json.load(f)
            sessions.append(self._session_from_metadata(path, metadata))

        return sessions

    def load_transcript(self, limit=20):
        session = self.ensure_current_session()
        if not session.messages_path.exists():
            return []

        with session.messages_path.open("r", encoding="utf-8") as f:
            messages = json.load(f)

        turns = []
        for message in messages[-limit:]:
            role = message.get("role", "")
            if role == "user":
                speaker = "You"
            elif role == "assistant":
                speaker = "Assistant"
            else:
                speaker = role or "Message"
            content = message.get("content", "")
            if role == "assistant" and message.get("process_entries"):
                content = {
                    "content": content,
                    "process_entries": list(message.get("process_entries") or []),
                    "process_collapsed": True,
                }
            turns.append((speaker, content))

        return turns

    def _session_from_metadata(self, path, metadata):
        messages_path = path / "messages.json"
        message_count = metadata.get("message_count")
        if message_count is None:
            message_count = self._count_messages(messages_path)

        return CLISession(
            id=metadata["id"],
            title=metadata.get("title", metadata["id"]),
            workspace=self.workspace,
            path=path,
            messages_path=messages_path,
            summary_path=path / "summary.md",
            profile_path=path / "profile.json",
            usage_path=path / "usage.json",
            runs_path=self.runs_dir / metadata["id"],
            updated_at=metadata.get("updated_at", ""),
            message_count=message_count,
        )

    def _write_metadata(self, session_path, metadata):
        with (session_path / "session.json").open("w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def _ensure_files(self, session_path):
        session_path.mkdir(parents=True, exist_ok=True)
        messages_path = session_path / "messages.json"
        summary_path = session_path / "summary.md"
        profile_path = session_path / "profile.json"
        if not messages_path.exists():
            messages_path.write_text("[]", encoding="utf-8")
        if not summary_path.exists():
            summary_path.write_text("", encoding="utf-8")
        if not profile_path.exists():
            profile_path.write_text("{}", encoding="utf-8")

    def _read_current_session_id(self):
        if not self.current_session_path.exists():
            return ""
        return self.current_session_path.read_text(encoding="utf-8").strip()

    def _write_current_session_id(self, session_id):
        self.current_session_path.parent.mkdir(parents=True, exist_ok=True)
        self.current_session_path.write_text(session_id, encoding="utf-8")

    def _next_default_title(self):
        existing = {
            session.title
            for session in self.list_sessions()
        }
        index = 1
        while f"新会话 {index}" in existing:
            index += 1
        return f"新会话 {index}"

    def _count_messages(self, messages_path):
        if not messages_path.exists():
            return 0
        with messages_path.open("r", encoding="utf-8") as f:
            return len(json.load(f))
