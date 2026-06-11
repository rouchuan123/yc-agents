from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def _new_run_id():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid4().hex[:8]
    return f"run_{timestamp}_{suffix}"


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class RunContext:
    user_input: str
    run_id: str = field(default_factory=_new_run_id)
    created_at: str = field(default_factory=_now_iso)
    selected_skill: str | None = None
    intent_result: dict | None = None
    outputs_dir: Path = field(init=False)

    def __post_init__(self):
        self.outputs_dir = Path("outputs/runs") / self.run_id