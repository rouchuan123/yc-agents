import subprocess
import time
from pathlib import Path

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools._workspace_paths import resolve_workspace_path, truncate_text
from yc_agents.tools.base import BaseTool


COMMANDS = {
    "pytest": {
        "command": ["pytest"],
        "heavy": False,
        "side_effect_note": "May write pytest cache inside the workspace.",
    },
    "python_pytest": {
        "command": ["python", "-m", "pytest"],
        "heavy": False,
        "side_effect_note": "May write pytest cache inside the workspace.",
    },
    "python_pytest_q": {
        "command": ["python", "-m", "pytest", "-q"],
        "heavy": False,
        "side_effect_note": "May write pytest cache inside the workspace.",
    },
    "mvn_test": {
        "command": ["mvn", "test"],
        "heavy": False,
        "side_effect_note": "May write target/ inside the workspace.",
    },
    "mvn_q_test": {
        "command": ["mvn", "-q", "test"],
        "heavy": False,
        "side_effect_note": "May write target/ inside the workspace.",
    },
    "mvnw_test": {
        "command": ["./mvnw", "test"],
        "heavy": False,
        "side_effect_note": "May write target/ inside the workspace.",
    },
    "gradle_test": {
        "command": ["gradle", "test"],
        "heavy": False,
        "side_effect_note": "May write build/ inside the workspace.",
    },
    "gradlew_test": {
        "command": ["./gradlew", "test"],
        "heavy": False,
        "side_effect_note": "May write build/ inside the workspace.",
    },
    "npm_test": {
        "command": ["npm", "test"],
        "heavy": False,
        "side_effect_note": "May write test caches inside the workspace.",
    },
    "npm_lint": {
        "command": ["npm", "run", "lint"],
        "heavy": False,
        "side_effect_note": "May write tool caches inside the workspace.",
    },
    "npm_typecheck": {
        "command": ["npm", "run", "typecheck"],
        "heavy": False,
        "side_effect_note": "Typecheck should not emit build output.",
    },
    "pnpm_test": {
        "command": ["pnpm", "test"],
        "heavy": False,
        "side_effect_note": "May write test caches inside the workspace.",
    },
    "pnpm_lint": {
        "command": ["pnpm", "lint"],
        "heavy": False,
        "side_effect_note": "May write tool caches inside the workspace.",
    },
    "pnpm_typecheck": {
        "command": ["pnpm", "typecheck"],
        "heavy": False,
        "side_effect_note": "Typecheck should not emit build output.",
    },
    "yarn_test": {
        "command": ["yarn", "test"],
        "heavy": False,
        "side_effect_note": "May write test caches inside the workspace.",
    },
    "yarn_lint": {
        "command": ["yarn", "lint"],
        "heavy": False,
        "side_effect_note": "May write tool caches inside the workspace.",
    },
    "yarn_typecheck": {
        "command": ["yarn", "typecheck"],
        "heavy": False,
        "side_effect_note": "Typecheck should not emit build output.",
    },
    "tsc_no_emit": {
        "command": ["tsc", "--noEmit"],
        "heavy": False,
        "side_effect_note": "TypeScript no-emit check should not write output.",
    },
    "npm_build": {
        "command": ["npm", "run", "build"],
        "heavy": True,
        "side_effect_note": "May write build output inside the workspace.",
    },
    "pnpm_build": {
        "command": ["pnpm", "build"],
        "heavy": True,
        "side_effect_note": "May write build output inside the workspace.",
    },
    "yarn_build": {
        "command": ["yarn", "build"],
        "heavy": True,
        "side_effect_note": "May write build output inside the workspace.",
    },
    "ruff_check": {
        "command": ["ruff", "check"],
        "heavy": True,
        "side_effect_note": "May write ruff cache inside the workspace.",
    },
}


class VerificationRunnerTool(BaseTool):
    name = "verification_runner"
    description = "Run allowlisted tests, lint, typecheck, and explicitly allowed heavy verification commands."
    schema = ToolSchema(
        fields=[
            ToolField(name="command_key", type="str", required=True),
            ToolField(name="workdir", type="str", required=False, default="."),
            ToolField(name="allow_heavy", type="bool", required=False, default=False),
            ToolField(name="timeout_seconds", type="int", required=False, default=120),
        ]
    )

    def __init__(self, workspace_root, max_output_chars=20000):
        self.workspace_root = Path(workspace_root).resolve()
        self.max_output_chars = max_output_chars

    def run(self, command_key, workdir=".", allow_heavy=False, timeout_seconds=120):
        if command_key not in COMMANDS:
            raise ValueError(f"Unsupported verification command key: {command_key}")

        spec = COMMANDS[command_key]
        if spec["heavy"] and not allow_heavy:
            raise PermissionError(
                f"Heavy verification command requires explicit user request: {command_key}"
            )

        cwd = resolve_workspace_path(self.workspace_root, workdir)
        if not cwd.exists() or not cwd.is_dir():
            raise FileNotFoundError(f"Verification workdir not found: {workdir}")

        started = time.monotonic()
        try:
            completed = subprocess.run(
                spec["command"],
                cwd=cwd,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=max(1, min(int(timeout_seconds or 120), 600)),
            )
            exit_code = completed.returncode
            stdout_text = completed.stdout
            stderr_text = completed.stderr
        except FileNotFoundError as exc:
            exit_code = None
            stdout_text = ""
            stderr_text = str(exc)
        duration = time.monotonic() - started
        stdout, stdout_truncated = truncate_text(stdout_text, self.max_output_chars)
        stderr, stderr_truncated = truncate_text(stderr_text, self.max_output_chars)
        return {
            "tool": self.name,
            "command_key": command_key,
            "ok": exit_code == 0,
            "command": spec["command"],
            "exit_code": exit_code,
            "duration_seconds": round(duration, 3),
            "workspace": str(self.workspace_root),
            "workdir": str(cwd.relative_to(self.workspace_root)) if cwd != self.workspace_root else ".",
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
            "heavy": spec["heavy"],
            "side_effect_note": spec["side_effect_note"],
        }
