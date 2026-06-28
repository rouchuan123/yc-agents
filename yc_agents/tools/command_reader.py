import subprocess
import time
from pathlib import Path

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools._workspace_paths import resolve_workspace_path, truncate_text
from yc_agents.tools.base import BaseTool


READ_ONLY_COMMANDS = {
    "rg_files",
    "rg_search",
    "git_status_short",
    "git_diff_stat",
    "git_diff_file",
    "pytest_collect_only",
}


class CommandReaderTool(BaseTool):
    name = "command_reader"
    description = (
        "Run a tiny allowlist of read-only project inspection commands. "
        "This is a fallback for development analysis, not a free shell."
    )
    schema = ToolSchema(
        fields=[
            ToolField(name="command_key", type="str", required=True),
            ToolField(name="pattern", type="str", required=False, default=""),
            ToolField(name="file_path", type="str", required=False, default=""),
            ToolField(name="path_glob", type="str", required=False, default=""),
            ToolField(name="workdir", type="str", required=False, default="."),
            ToolField(name="target", type="str", required=False, default=""),
            ToolField(name="use_regex", type="bool", required=False, default=False),
            ToolField(name="max_results", type="int", required=False, default=50),
            ToolField(name="timeout_seconds", type="int", required=False, default=15),
        ]
    )

    def __init__(self, workspace_root, max_output_chars=20000):
        self.workspace_root = Path(workspace_root).resolve()
        self.max_output_chars = max_output_chars

    def run(
        self,
        command_key,
        pattern="",
        file_path="",
        path_glob="",
        workdir=".",
        target="",
        use_regex=False,
        max_results=50,
        timeout_seconds=15,
    ):
        if command_key not in READ_ONLY_COMMANDS:
            raise ValueError(f"Unsupported command_reader command key: {command_key}")

        cwd = self._resolve_workdir(workdir)
        command = self._build_command(
            command_key=command_key,
            pattern=pattern,
            file_path=file_path,
            path_glob=path_glob,
            cwd=cwd,
            target=target,
            use_regex=use_regex,
        )
        return self._run_command(command_key, command, cwd, max_results, timeout_seconds)

    def _resolve_workdir(self, workdir):
        cwd = resolve_workspace_path(self.workspace_root, workdir or ".")
        if not cwd.exists() or not cwd.is_dir():
            raise FileNotFoundError(f"command_reader workdir not found: {workdir}")
        return cwd

    def _safe_path_glob(self, path_glob):
        path_glob = str(path_glob or "").strip()
        if not path_glob:
            return ""
        normalized = path_glob.replace("\\", "/")
        if normalized.startswith("/") or ":" in normalized or ".." in normalized.split("/"):
            raise PermissionError(f"Path glob escapes active workspace: {path_glob}")
        return normalized

    def _workspace_relative_path(self, file_path):
        if not str(file_path or "").strip():
            raise ValueError("file_path is required for git_diff_file")
        path = resolve_workspace_path(self.workspace_root, file_path)
        return str(path.relative_to(self.workspace_root)).replace("\\", "/")

    def _workspace_relative_target(self, target, cwd):
        if not str(target or "").strip():
            return ""
        path = resolve_workspace_path(self.workspace_root, target)
        try:
            return str(path.relative_to(cwd)).replace("\\", "/")
        except ValueError:
            return str(path)

    def _build_command(self, command_key, pattern, file_path, path_glob, cwd, target, use_regex):
        if command_key == "rg_files":
            command = ["rg", "--files"]
            safe_glob = self._safe_path_glob(path_glob)
            if safe_glob:
                command.extend(["-g", safe_glob])
            return command

        if command_key == "rg_search":
            pattern = str(pattern or "")
            if not pattern:
                raise ValueError("pattern is required for rg_search")
            command = ["rg", "--line-number", "--with-filename", "--color", "never"]
            if not use_regex:
                command.append("--fixed-strings")
            safe_glob = self._safe_path_glob(path_glob)
            if safe_glob:
                command.extend(["-g", safe_glob])
            command.append(pattern)
            return command

        if command_key == "git_status_short":
            return ["git", "status", "--short"]

        if command_key == "git_diff_stat":
            return ["git", "diff", "--stat"]

        if command_key == "git_diff_file":
            return ["git", "diff", "--", self._workspace_relative_path(file_path)]

        if command_key == "pytest_collect_only":
            command = ["python", "-m", "pytest", "--collect-only"]
            relative_target = self._workspace_relative_target(target, cwd)
            if relative_target:
                command.append(relative_target)
            return command

        raise ValueError(f"Unsupported command_reader command key: {command_key}")

    def _run_command(self, command_key, command, cwd, max_results, timeout_seconds):
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=max(1, min(int(timeout_seconds or 15), 120)),
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
        parsed = self._parse_output(command_key, stdout_text, max_results)
        return {
            "tool": self.name,
            "command_key": command_key,
            "ok": self._is_ok(command_key, exit_code),
            "command": command,
            "exit_code": exit_code,
            "duration_seconds": round(duration, 3),
            "workspace": str(self.workspace_root),
            "workdir": str(cwd.relative_to(self.workspace_root)) if cwd != self.workspace_root else ".",
            "stdout": stdout,
            "stderr": stderr,
            "raw_output": stdout,
            "truncated": stdout_truncated or stderr_truncated,
            "parsed": parsed,
        }

    def _is_ok(self, command_key, exit_code):
        if command_key == "rg_search":
            return exit_code in {0, 1}
        return exit_code == 0

    def _parse_output(self, command_key, stdout_text, max_results):
        max_results = max(1, min(int(max_results or 50), 500))
        lines = stdout_text.splitlines()[:max_results]

        if command_key == "rg_files":
            return {"files": [line.replace("\\", "/") for line in lines]}

        if command_key == "rg_search":
            matches = []
            for raw_line in lines:
                parts = raw_line.split(":", 2)
                if len(parts) != 3:
                    continue
                path, line_number, text = parts
                matches.append(
                    {
                        "path": path.replace("\\", "/"),
                        "line": int(line_number),
                        "text": text,
                    }
                )
            return {"matches": matches}

        if command_key == "git_status_short":
            return {"status_lines": lines}

        if command_key == "git_diff_stat":
            return {"diff_stat_lines": lines}

        if command_key == "git_diff_file":
            return {"diff_lines": lines}

        if command_key == "pytest_collect_only":
            return {"output_lines": lines}

        return {"output_lines": lines}
