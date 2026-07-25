import os
import subprocess
import sys
import time
from pathlib import Path


SAFE_ENV_KEYS = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "LOCALAPPDATA",
    "APPDATA",
    "USERPROFILE",
    "COMSPEC",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "COMMONPROGRAMFILES",
    "PYTHONUTF8",
}


class ExecutionBroker:
    """Allowlisted local process broker. This is not an OS-level sandbox."""

    def __init__(self, read_roots, write_roots, timeout_seconds=180, max_output_chars=20000):
        self.read_roots = [Path(root).resolve() for root in read_roots]
        self.write_roots = [Path(root).resolve() for root in write_roots]
        self.timeout_seconds = int(timeout_seconds)
        self.max_output_chars = int(max_output_chars)

    def run(self, command_key, input_path, output_path, timeout_seconds=None):
        input_path = self._validate_path(input_path, self.read_roots, must_exist=True)
        output_path = self._validate_path(output_path, self.write_roots, must_exist=False)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = self._build_command(command_key, input_path, output_path)
        env = {key: value for key, value in os.environ.items() if key.upper() in SAFE_ENV_KEYS}
        env.setdefault("PYTHONUTF8", "1")
        started = time.monotonic()
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen(
            command,
            cwd=str(output_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=creationflags,
        )
        timeout = max(1, min(int(timeout_seconds or self.timeout_seconds), 900))
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate_tree(process)
            stdout, stderr = process.communicate()
        duration = time.monotonic() - started
        return {
            "ok": not timed_out and process.returncode == 0 and output_path.exists(),
            "command_key": command_key,
            "command": command,
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "duration_seconds": round(duration, 3),
            "stdout": (stdout or "")[: self.max_output_chars],
            "stderr": (stderr or "")[: self.max_output_chars],
            "input": str(input_path),
            "output": str(output_path),
            "environment_keys": sorted(env),
            "network_policy": "not_enforced_local_backend",
            "write_scope": [str(root) for root in self.write_roots],
        }

    @staticmethod
    def _build_command(command_key, input_path, output_path):
        if command_key == "word_export_pdf":
            helper = Path(__file__).resolve().with_name("word_renderer.py")
            return [
                sys.executable,
                str(helper),
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
        raise ValueError(f"ExecutionBroker command is not allowlisted: {command_key}")

    @staticmethod
    def _validate_path(path, roots, must_exist):
        resolved = Path(path).resolve()
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise PermissionError(f"ExecutionBroker path is outside the allowed scope: {path}")
        if must_exist and (not resolved.exists() or not resolved.is_file()):
            raise FileNotFoundError(f"ExecutionBroker input not found: {path}")
        return resolved

    @staticmethod
    def _terminate_tree(process):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            process.kill()
