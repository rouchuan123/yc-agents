import json
import subprocess
import threading


class StdioMCPClient:
    def __init__(self, command, server_name, timeout_seconds=10):
        self.command = list(command)
        self.server_name = server_name
        self.timeout_seconds = timeout_seconds
        self.process = None
        self._next_id = 1
        self._lock = threading.Lock()
        self.startup_error = None

    def start(self):
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self.request("initialize", {})
        except Exception as exc:
            self.startup_error = str(exc)
            self.close()
            raise
        return self

    def list_tools(self):
        response = self.request("tools/list", {})
        return response.get("tools", [])

    def call_tool(self, server_name, tool_name, arguments):
        if server_name != self.server_name:
            return {
                "ok": False,
                "error_type": "wrong_server",
                "error": f"Expected server {self.server_name}, got {server_name}",
            }
        if self.process is None or self.process.poll() is not None:
            return {
                "ok": False,
                "error_type": "mcp_server_unavailable",
                "error": self.startup_error or "MCP server is not running",
            }
        return self.request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )

    def request(self, method, params):
        with self._lock:
            if (
                self.process is None
                or self.process.stdin is None
                or self.process.stdout is None
            ):
                raise RuntimeError("MCP server is not running")

            request_id = self._next_id
            self._next_id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed stdout")

            response = json.loads(line)
            if response.get("id") != request_id:
                raise RuntimeError(
                    f"MCP response id mismatch: {response.get('id')} != {request_id}"
                )
            if "error" in response:
                raise RuntimeError(response["error"].get("message", "MCP error"))
            return response.get("result", {})

    def close(self):
        process = self.process
        self.process = None
        if process is None:
            return

        if process.stdin is not None:
            try:
                process.stdin.close()
            except Exception:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except Exception:
                process.kill()
