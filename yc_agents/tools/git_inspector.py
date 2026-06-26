import re
import subprocess
from pathlib import Path

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools._workspace_paths import resolve_workspace_path, truncate_text
from yc_agents.tools.base import BaseTool


SAFE_REF_RE = re.compile(r"^[A-Za-z0-9._/@:+-]+$")


class GitInspectorTool(BaseTool):
    name = "git_inspector"
    description = "Inspect Git status, diffs, commits, logs, and blame using read-only local operations."
    schema = ToolSchema(
        fields=[
            ToolField(name="operation", type="str", required=True),
            ToolField(name="ref", type="str", required=False, default="HEAD"),
            ToolField(name="base_ref", type="str", required=False, default=""),
            ToolField(name="head_ref", type="str", required=False, default="HEAD"),
            ToolField(name="file_path", type="str", required=False, default=""),
            ToolField(name="limit", type="int", required=False, default=20),
        ]
    )

    def __init__(self, workspace_root, timeout_seconds=20, max_output_chars=20000):
        self.workspace_root = Path(workspace_root).resolve()
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def run(self, operation, ref="HEAD", base_ref="", head_ref="HEAD", file_path="", limit=20):
        operations = {
            "status": self._status,
            "diff_worktree": self._diff_worktree,
            "diff_staged": self._diff_staged,
            "show_commit": lambda: self._show_commit(ref),
            "log": lambda: self._log(limit),
            "blame": lambda: self._blame(file_path, ref),
            "diff_refs": lambda: self._diff_refs(base_ref, head_ref),
        }
        if operation not in operations:
            raise ValueError(f"Unsupported git_inspector operation: {operation}")

        return operations[operation]()

    def _status(self):
        branch = self._git(["branch", "--show-current"])
        status = self._git(["status", "--short", "--branch"])
        raw, truncated = truncate_text(status["stdout"], self.max_output_chars)
        return {
            "tool": self.name,
            "operation": "status",
            "ok": status["exit_code"] == 0,
            "command": status["command"],
            "exit_code": status["exit_code"],
            "workspace": str(self.workspace_root),
            "branch": branch["stdout"].strip(),
            "status": self._parse_status(status["stdout"]),
            "raw_output": raw,
            "stderr": status["stderr"],
            "truncated": truncated,
            "notes": [],
        }

    def _diff_worktree(self):
        return self._diff(["diff"], "diff_worktree")

    def _diff_staged(self):
        return self._diff(["diff", "--staged"], "diff_staged")

    def _show_commit(self, ref):
        safe_ref = self._validate_ref(ref)
        result = self._git(["show", "--stat", "--patch", safe_ref])
        raw, truncated = truncate_text(result["stdout"], self.max_output_chars)
        return {
            "tool": self.name,
            "operation": "show_commit",
            "ok": result["exit_code"] == 0,
            "command": result["command"],
            "exit_code": result["exit_code"],
            "workspace": str(self.workspace_root),
            "commit": safe_ref,
            "changed_files": self._changed_files_for(["show", "--numstat", "--format=", safe_ref]),
            "raw_output": raw,
            "stderr": result["stderr"],
            "truncated": truncated,
            "notes": [],
        }

    def _log(self, limit):
        limit = max(1, min(int(limit or 20), 100))
        result = self._git(["log", f"--max-count={limit}", "--oneline", "--decorate"])
        raw, truncated = truncate_text(result["stdout"], self.max_output_chars)
        return {
            "tool": self.name,
            "operation": "log",
            "ok": result["exit_code"] == 0,
            "command": result["command"],
            "exit_code": result["exit_code"],
            "workspace": str(self.workspace_root),
            "commits": [line for line in result["stdout"].splitlines() if line.strip()],
            "raw_output": raw,
            "stderr": result["stderr"],
            "truncated": truncated,
            "notes": [],
        }

    def _blame(self, file_path, ref):
        safe_ref = self._validate_ref(ref)
        path = resolve_workspace_path(self.workspace_root, file_path)
        relative = str(path.relative_to(self.workspace_root)).replace("\\", "/")
        result = self._git(["blame", safe_ref, "--", relative])
        raw, truncated = truncate_text(result["stdout"], self.max_output_chars)
        return {
            "tool": self.name,
            "operation": "blame",
            "ok": result["exit_code"] == 0,
            "command": result["command"],
            "exit_code": result["exit_code"],
            "workspace": str(self.workspace_root),
            "path": relative,
            "raw_output": raw,
            "stderr": result["stderr"],
            "truncated": truncated,
            "notes": [],
        }

    def _diff_refs(self, base_ref, head_ref):
        safe_base = self._validate_ref(base_ref)
        safe_head = self._validate_ref(head_ref)
        spec = f"{safe_base}...{safe_head}"
        result = self._git(["diff", "--stat", "--patch", spec])
        raw, truncated = truncate_text(result["stdout"], self.max_output_chars)
        changed_files = self._changed_files_for(["diff", "--numstat", spec])
        return {
            "tool": self.name,
            "operation": "diff_refs",
            "ok": result["exit_code"] == 0,
            "command": result["command"],
            "exit_code": result["exit_code"],
            "workspace": str(self.workspace_root),
            "base_ref": safe_base,
            "head_ref": safe_head,
            "changed_files": changed_files,
            "summary": self._summary(changed_files),
            "raw_output": raw,
            "stderr": result["stderr"],
            "truncated": truncated,
            "notes": ["Remote refs were not fetched; result is based on local refs."],
        }

    def _diff(self, args, operation):
        result = self._git(args + ["--stat", "--patch"])
        changed_files = self._changed_files_for(args + ["--numstat"])
        raw, truncated = truncate_text(result["stdout"], self.max_output_chars)
        return {
            "tool": self.name,
            "operation": operation,
            "ok": result["exit_code"] == 0,
            "command": result["command"],
            "exit_code": result["exit_code"],
            "workspace": str(self.workspace_root),
            "changed_files": changed_files,
            "summary": self._summary(changed_files),
            "raw_output": raw,
            "stderr": result["stderr"],
            "truncated": truncated,
            "notes": [],
        }

    def _changed_files_for(self, git_args):
        result = self._git(git_args)
        files = []
        for line in result["stdout"].splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            additions = self._parse_count(parts[0])
            deletions = self._parse_count(parts[1])
            files.append(
                {
                    "path": parts[2],
                    "status": "modified",
                    "additions": additions,
                    "deletions": deletions,
                }
            )
        return files

    def _git(self, args):
        completed = subprocess.run(
            ["git", *args],
            cwd=self.workspace_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.timeout_seconds,
        )
        return {
            "command": ["git", *args],
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def _validate_ref(self, ref):
        ref = str(ref or "").strip()
        if not ref:
            raise ValueError("Git ref is required")
        if ".." in ref.replace("...", ""):
            raise ValueError(f"Unsafe git ref: {ref}")
        if not SAFE_REF_RE.match(ref):
            raise ValueError(f"Unsafe git ref: {ref}")
        return ref

    def _parse_status(self, stdout):
        rows = []
        for line in stdout.splitlines():
            if not line or line.startswith("## "):
                continue
            rows.append({"status": line[:2].strip(), "path": line[3:].strip()})
        return rows

    def _parse_count(self, value):
        return 0 if value == "-" else int(value)

    def _summary(self, changed_files):
        return {
            "files_changed": len(changed_files),
            "additions": sum(item["additions"] for item in changed_files),
            "deletions": sum(item["deletions"] for item in changed_files),
        }
