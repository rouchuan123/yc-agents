from dataclasses import dataclass


@dataclass(frozen=True)
class CLICommand:
    action: str
    content: str = ""


def parse_cli_input(text):
    content = text.strip()

    if not content:
        return CLICommand("ignore", "")

    if not content.startswith("/"):
        return CLICommand("message", content)

    normalized = content.lower()

    if normalized in {"/exit", "/quit"}:
        return CLICommand("exit", "")

    if normalized == "/status":
        return CLICommand("status", "")

    if normalized == "/context":
        return CLICommand("context", "")

    if normalized == "/stop":
        return CLICommand("stop", "")

    if normalized == "/skills":
        return CLICommand("skills", "")

    if normalized == "/clear":
        return CLICommand("clear", "")

    if normalized == "/attachments":
        return CLICommand("attachments", "")

    if normalized.startswith("/attach "):
        return CLICommand("attach", content[len("/attach "):].strip())

    if normalized.startswith("/detach "):
        return CLICommand("detach", content[len("/detach "):].strip())

    if normalized == "/document status":
        return CLICommand("document_status", "")

    if normalized == "/document history":
        return CLICommand("document_history", "")

    if normalized.startswith("/document rollback "):
        return CLICommand(
            "document_rollback",
            content[len("/document rollback "):].strip(),
        )

    if normalized == "/confirm":
        return CLICommand("confirm", "")

    if normalized == "/cancel":
        return CLICommand("cancel", "")

    if normalized == "/session":
        return CLICommand("session_list", "")

    if normalized.startswith("/session "):
        argument = content[len("/session "):].strip()
        argument_lower = argument.lower()
        if argument_lower == "new":
            return CLICommand("session_new", "")
        if argument_lower.startswith("new "):
            return CLICommand("session_new", argument[4:].strip())
        if argument_lower == "delete":
            return CLICommand("session_delete", "")
        if argument_lower.startswith("delete "):
            return CLICommand("session_delete", argument[7:].strip())
        if argument:
            return CLICommand("session_switch", argument)

    if normalized == "/workspace":
        return CLICommand("workspace_list", "")

    if normalized.startswith("/workspace "):
        argument = content[len("/workspace "):].strip()
        argument_lower = argument.lower()
        if argument_lower == "current":
            return CLICommand("workspace_current", "")
        if argument_lower.startswith("add "):
            return CLICommand("workspace_add", argument[4:].strip())
        if argument_lower == "delete":
            return CLICommand("workspace_delete", "")
        if argument_lower.startswith("delete "):
            return CLICommand("workspace_delete", argument[7:].strip())
        if argument:
            return CLICommand("workspace_switch", argument)

    return CLICommand("unknown", content)
