from pathlib import Path


MAX_RAW_OUTPUT_CHARS = 20000


def resolve_workspace_path(workspace_root, path="."):
    root = Path(workspace_root).resolve()
    candidate = Path(str(path or ".").strip())
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()

    if resolved != root and root not in resolved.parents:
        raise PermissionError(f"Path escapes active workspace: {path}")

    return resolved


def truncate_text(text, max_chars=MAX_RAW_OUTPUT_CHARS):
    text = text or ""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n... [truncated]", True
