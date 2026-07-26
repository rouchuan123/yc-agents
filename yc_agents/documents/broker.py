import json
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

# Job Object 尽力而为加固的参数：渲染子进程内存上限与活跃进程数上限。
JOB_OBJECT_MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
JOB_OBJECT_ACTIVE_PROCESS_LIMIT = 4

JOB_OBJECT_NOTE = (
    "Job Object 仅覆盖 broker 启动的 python 渲染子进程树；"
    "Word 是 out-of-process COM 服务（WINWORD.EXE 由系统 COM 基础设施拉起），"
    "不在该进程树内，属预期限制。超时兜底仍依赖 taskkill 进程树清理。"
)


def _create_job_limiter(pid):
    """把渲染子进程放进 Windows Job Object：关句柄即杀（防孤儿）、
    2GB 内存上限、活跃进程数上限。win32job 不可用或调用失败时由调用方
    优雅回退——加固失败绝不能影响渲染本身。"""
    import win32api
    import win32con
    import win32job

    job = win32job.CreateJobObject(None, "")
    info = win32job.QueryInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation
    )
    info["BasicLimitInformation"]["LimitFlags"] = (
        win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
        | win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    )
    info["ProcessMemoryLimit"] = JOB_OBJECT_MEMORY_LIMIT_BYTES
    info["BasicLimitInformation"]["ActiveProcessLimit"] = (
        JOB_OBJECT_ACTIVE_PROCESS_LIMIT
    )
    win32job.SetInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation, info
    )
    process_handle = win32api.OpenProcess(
        win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, pid
    )
    try:
        win32job.AssignProcessToJobObject(job, process_handle)
    finally:
        win32api.CloseHandle(process_handle)

    def release():
        win32api.CloseHandle(job)

    return release


class ExecutionBroker:
    """Allowlisted local process broker. This is not an OS-level sandbox.

    诚实化说明：read/write 作用域与网络策略只是"声明"，broker 并没有
    OS 级机制强制执行它们，所以结果字段用 declared_* 命名并固定携带
    enforced=False；渲染完成后会复核输出目录，把声明之外的意外新文件
    记进 out_of_scope_writes（仅审计记录，不删除）。Windows 上会尽力用
    Job Object 包住渲染子进程树（见 _create_job_limiter），失败时结果
    记 job_object='unavailable' 并继续渲染。
    """

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
        files_before = self._snapshot_files(output_path.parent)
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
        job_object = "unavailable"
        release_job = None
        try:
            release_job = _create_job_limiter(process.pid)
            job_object = "active"
        except Exception:
            # pywin32 缺失、进程已退出、宿主自身在不可嵌套的 Job 里……
            # 一律回退为无加固运行，不影响渲染。
            job_object = "unavailable"
        timeout = max(1, min(int(timeout_seconds or self.timeout_seconds), 900))
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate_tree(process)
            stdout, stderr = process.communicate()
        finally:
            if release_job is not None:
                try:
                    release_job()
                except Exception:
                    pass
        duration = time.monotonic() - started
        out_of_scope_writes = self._audit_output_dir(
            output_path.parent, files_before, output_path
        )
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
            # 声明而非强制执行：broker 只是 allowlist 进程代理，不是沙箱。
            "declared_network_policy": "not_enforced_local_backend",
            "declared_write_scope": [str(root) for root in self.write_roots],
            "enforced": False,
            "security_degraded": self._extract_security_degraded(stdout),
            "out_of_scope_writes": out_of_scope_writes,
            "job_object": job_object,
            "job_object_note": JOB_OBJECT_NOTE,
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
    def _snapshot_files(directory):
        directory = Path(directory)
        if not directory.exists():
            return set()
        try:
            return {path for path in directory.rglob("*") if path.is_file()}
        except OSError:
            return set()

    def _audit_output_dir(self, directory, files_before, expected_output):
        """渲染后复核输出目录：声明的写入物只有 expected_output 一个，
        其余新出现的文件都属声明之外的意外写入。broker 无沙箱、无法
        监控全盘，所以审计范围限于它能看到的输出目录；仅记录不删除。"""
        new_files = self._snapshot_files(directory) - files_before
        unexpected = [
            str(path)
            for path in new_files
            if path != Path(expected_output).resolve()
        ]
        return sorted(unexpected)

    @staticmethod
    def _extract_security_degraded(stdout_text):
        """word_renderer 把安全设置降级清单放进它 stdout 的 JSON 结果；
        从最后一行 JSON 里提出来，方便 verifier 直接消费而不用重新解析
        子进程输出。"""
        for line in reversed((stdout_text or "").strip().splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if isinstance(payload, dict):
                return [str(item) for item in payload.get("security_degraded") or []]
        return []

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
