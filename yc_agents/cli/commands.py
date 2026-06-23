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

    if normalized == "/clear":
        return CLICommand("clear", "")

    return CLICommand("unknown", content)
