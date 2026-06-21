from pathlib import Path


DEFAULT_DANGEROUS_TOOLS = {
    "script_runner",
    "shell",
    "mcp_write",
}


class HumanApprovalGate:
    def __init__(self, project_root=".", dangerous_tools=None):
        self.project_root = Path(project_root).resolve()
        self.dangerous_tools = set(dangerous_tools or DEFAULT_DANGEROUS_TOOLS)

    def check_tool_call(self, tool_name, arguments=None):
        arguments = arguments or {}

        if tool_name in self.dangerous_tools:
            return self._needs_approval(
                action="tool_call",
                reason=f"Tool requires human approval: {tool_name}",
                tool_name=tool_name,
                arguments=arguments,
            )

        return self._allowed(
            action="tool_call",
            reason=f"Tool call is allowed: {tool_name}",
            tool_name=tool_name,
            arguments=arguments,
        )

    def check_file_write(self, file_path, overwrite=False):
        resolved_path = (self.project_root / Path(file_path)).resolve()

        if resolved_path.exists() and not overwrite:
            return self._needs_approval(
                action="file_write",
                reason=f"File already exists and overwrite was not approved: {file_path}",
                file_path=str(resolved_path),
            )

        return self._allowed(
            action="file_write",
            reason=f"File write is allowed: {file_path}",
            file_path=str(resolved_path),
        )

    def _allowed(self, **payload):
        return {
            "allowed": True,
            "needs_approval": False,
            **payload,
        }

    def _needs_approval(self, **payload):
        return {
            "allowed": False,
            "needs_approval": True,
            **payload,
        }
