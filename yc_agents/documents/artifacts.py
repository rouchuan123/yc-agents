from pathlib import Path


class ArtifactRegistry:
    def __init__(self):
        self.items = []

    def collect_tool_result(self, tool_name, result):
        if not isinstance(result, dict):
            return []
        added = []
        for value in result.get("artifacts", []):
            path = Path(value)
            item = {
                "tool": tool_name,
                "path": str(path),
                "name": path.name,
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() and path.is_file() else None,
            }
            self.items.append(item)
            added.append(item)
        return added
