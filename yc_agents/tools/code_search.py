import subprocess
from pathlib import Path

from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.tools._workspace_paths import resolve_workspace_path, truncate_text
from yc_agents.tools.base import BaseTool


class CodeSearchTool(BaseTool):
    name = "code_search"
    description = "Search workspace files and return small context snippets without full-file reading."
    schema = ToolSchema(
        fields=[
            ToolField(name="operation", type="str", required=True),
            ToolField(name="pattern", type="str", required=False, default=""),
            ToolField(name="file_path", type="str", required=False, default=""),
            ToolField(name="line", type="int", required=False, default=1),
            ToolField(name="context_lines", type="int", required=False, default=2),
            ToolField(name="max_results", type="int", required=False, default=50),
        ]
    )

    def __init__(self, workspace_root, timeout_seconds=10, max_output_chars=20000):
        self.workspace_root = Path(workspace_root).resolve()
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def run(self, operation, pattern="", file_path="", line=1, context_lines=2, max_results=50):
        if operation == "list_files":
            return self._list_files(max_results)
        if operation == "search":
            return self._search(pattern, context_lines, max_results)
        if operation == "snippet":
            return self._snippet(file_path, line, context_lines)
        raise ValueError(f"Unsupported code_search operation: {operation}")

    def _list_files(self, max_results):
        files, raw = self._rg_files(max_results)
        raw_output, truncated = truncate_text(raw, self.max_output_chars)
        return {
            "tool": self.name,
            "operation": "list_files",
            "ok": True,
            "files": files,
            "count": len(files),
            "raw_output": raw_output,
            "truncated": truncated,
        }

    def _search(self, pattern, context_lines, max_results):
        pattern = str(pattern or "")
        if not pattern:
            raise ValueError("Search pattern is required")
        max_results = max(1, min(int(max_results or 50), 200))
        context_lines = max(0, min(int(context_lines or 0), 5))

        completed = subprocess.run(
            ["rg", "--line-number", "--with-filename", "--color", "never", pattern],
            cwd=self.workspace_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.timeout_seconds,
        )
        lines = completed.stdout.splitlines()[:max_results]
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
                    "before": self._context(path, int(line_number), context_lines, before=True),
                    "after": self._context(path, int(line_number), context_lines, before=False),
                }
            )

        raw_output, truncated = truncate_text(completed.stdout, self.max_output_chars)
        return {
            "tool": self.name,
            "operation": "search",
            "ok": completed.returncode in {0, 1},
            "pattern": pattern,
            "matches": matches,
            "count": len(matches),
            "stderr": completed.stderr,
            "raw_output": raw_output,
            "truncated": truncated or len(completed.stdout.splitlines()) > max_results,
        }

    def _snippet(self, file_path, line, context_lines):
        path = resolve_workspace_path(self.workspace_root, file_path)
        relative = str(path.relative_to(self.workspace_root)).replace("\\", "/")
        text_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        line = max(1, int(line or 1))
        context_lines = max(0, min(int(context_lines or 0), 20))
        start = max(1, line - context_lines)
        end = min(len(text_lines), line + context_lines)
        rows = [
            {"line": number, "text": text_lines[number - 1]}
            for number in range(start, end + 1)
        ]
        raw_output = "\n".join(f"{row['line']}: {row['text']}" for row in rows)
        raw_output, truncated = truncate_text(raw_output, self.max_output_chars)
        return {
            "tool": self.name,
            "operation": "snippet",
            "ok": True,
            "path": relative,
            "start_line": start,
            "end_line": end,
            "lines": rows,
            "raw_output": raw_output,
            "truncated": truncated,
        }

    def _rg_files(self, max_results):
        max_results = max(1, min(int(max_results or 50), 1000))
        try:
            completed = subprocess.run(
                ["rg", "--files"],
                cwd=self.workspace_root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError:
            completed = None

        if completed is not None and completed.returncode == 0:
            files = [line.replace("\\", "/") for line in completed.stdout.splitlines()[:max_results]]
            return files, completed.stdout

        files = []
        for path in sorted(self.workspace_root.rglob("*")):
            relative_parts = path.relative_to(self.workspace_root).parts
            if path.is_file() and ".git" not in relative_parts:
                files.append(str(path.relative_to(self.workspace_root)).replace("\\", "/"))
            if len(files) >= max_results:
                break
        return files, "\n".join(files)

    def _context(self, file_path, line_number, count, before):
        if count <= 0:
            return []
        path = resolve_workspace_path(self.workspace_root, file_path)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if before:
            start = max(1, line_number - count)
            end = line_number - 1
        else:
            start = line_number + 1
            end = min(len(lines), line_number + count)
        return [lines[number - 1] for number in range(start, end + 1)]
