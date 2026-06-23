from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from yc_agents.cli.formatting import format_context_usage, middle_truncate


@dataclass(frozen=True)
class CLIStatus:
    workspace: Path
    model: str
    context_used: int
    context_limit: int
    branch: str
    session_id: str

    def first_row(self, width=100):
        left = "YC Agents"
        right = f"Session {self.session_id}"

        if width <= len(left) + len(right) + 1:
            return middle_truncate(f"{left} {right}", width)

        return f"{left}{' ' * (width - len(left) - len(right))}{right}"

    def second_row(self, width=100):
        parts = [
            f"Workspace {middle_truncate(str(self.workspace), 36)}",
            f"Model {middle_truncate(self.model, 24)}",
            f"Context {format_context_usage(self.context_used, self.context_limit)}",
            f"Branch {middle_truncate(self.branch, 24)}",
        ]
        return middle_truncate("   ".join(parts), width)

    def summary(self, width=100):
        return f"{self.first_row(width)}\n{self.second_row(width)}"


class StatusCollector:
    def __init__(
        self,
        workspace_provider=None,
        model_provider=None,
        context_provider=None,
        branch_provider=None,
        session_id=None,
        context_limit=8000,
    ):
        self.workspace_provider = workspace_provider or (lambda: Path.cwd())
        self.model_provider = model_provider or (lambda: "unknown")
        self.context_provider = context_provider or (lambda: 0)
        self.branch_provider = branch_provider or (lambda: "no-git")
        self.session_id = session_id or f"session-{uuid4().hex[:8]}"
        self.context_limit = context_limit

    def collect(self):
        return CLIStatus(
            workspace=self._safe_workspace(),
            model=self._safe_model(),
            context_used=self._safe_context_used(),
            context_limit=self.context_limit,
            branch=self._safe_branch(),
            session_id=self.session_id,
        )

    def _safe_workspace(self):
        try:
            return Path(self.workspace_provider()).resolve()
        except Exception:
            return Path(".").resolve()

    def _safe_model(self):
        try:
            model = self.model_provider()
        except Exception:
            return "unknown"

        return str(model or "unknown")

    def _safe_context_used(self):
        try:
            used = int(self.context_provider() or 0)
        except Exception:
            return 0

        return max(0, used)

    def _safe_branch(self):
        try:
            branch = self.branch_provider()
        except Exception:
            return "no-git"

        return str(branch or "no-git")
