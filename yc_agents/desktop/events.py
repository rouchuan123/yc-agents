import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DesktopEvent:
    type: str
    project_id: str
    session_id: str
    run_id: str
    payload: dict = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self):
        return asdict(self)
