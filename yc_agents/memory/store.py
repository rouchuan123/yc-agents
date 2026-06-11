import json
from pathlib import Path


class MemoryStore:
    def __init__(self, memory_dir="data/memory"):
        self.memory_dir = Path(memory_dir)

    def read_json(self, file_name, default=None):
        path = self.memory_dir / file_name

        if not path.exists():
            return default

        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def write_json(self, file_name, data):
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        path = self.memory_dir / file_name

        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return path