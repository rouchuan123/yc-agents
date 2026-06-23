import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class CodeProjectService:
    def __init__(self, thesis_root):
        self.thesis_root = Path(thesis_root).resolve()
        self.bindings_path = self.thesis_root / "code_projects" / "bindings.json"

    def bind(self, name, path):
        path = Path(path).resolve()
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(path)

        data = self._load()
        binding = {
            "id": f"code_{uuid.uuid4().hex[:12]}",
            "name": name,
            "path": str(path),
            "mode": "read_only",
            "added_at": utc_now_iso(),
            "selected_files": [],
        }
        data["projects"].append(binding)
        self._save(data)
        return binding

    def list_projects(self):
        return self._load()["projects"]

    def tree(self, project_id):
        binding = self._get(project_id)
        root = Path(binding["path"]).resolve()
        items = []

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
                continue
            items.append(
                {
                    "name": path.name,
                    "relative_path": path.relative_to(root).as_posix(),
                    "size": path.stat().st_size,
                }
            )

        return items

    def select_files(self, project_id, relative_paths):
        binding = self._get(project_id)
        root = Path(binding["path"]).resolve()
        selected = []

        for relative_path in relative_paths:
            path = (root / relative_path).resolve()
            if not self._is_relative_to(path, root):
                raise ValueError(f"Path is outside code project: {relative_path}")
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(relative_path)
            selected.append(Path(relative_path).as_posix())

        data = self._load()
        for project in data["projects"]:
            if project["id"] == project_id:
                project["selected_files"] = selected
                self._save(data)
                return project

        raise KeyError(project_id)

    def _get(self, project_id):
        for project in self._load()["projects"]:
            if project["id"] == project_id:
                return project
        raise KeyError(project_id)

    def _load(self):
        if not self.bindings_path.exists():
            return {"projects": []}
        with self.bindings_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data):
        self.bindings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.bindings_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _is_relative_to(self, path, parent):
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False
