import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIRECTORIES = [
    "documents/literature",
    "documents/notes",
    "documents/requirements",
    "documents/thesis",
    "code_projects",
    "sessions",
    "runs",
    "memory",
    "exports",
]


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
    def create_project(self, root, name):
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)

        for directory in PROJECT_DIRECTORIES:
            (root / directory).mkdir(parents=True, exist_ok=True)

        project = {
            "id": f"thesis_{uuid.uuid4().hex[:12]}",
            "name": name,
            "created_at": utc_now_iso(),
            "documents_dir": "documents",
            "runs_dir": "runs",
            "memory_dir": "memory",
            "settings": {
                "default_skill": None,
                "language": "zh-CN",
            },
            "root": str(root),
        }

        self._write_json(
            root / "project.json",
            {key: value for key, value in project.items() if key != "root"},
        )
        return project

    def open_project(self, root):
        root = Path(root).resolve()
        project_path = root / "project.json"

        if not project_path.exists():
            raise FileNotFoundError(f"Project file not found: {project_path}")

        with project_path.open("r", encoding="utf-8") as f:
            project = json.load(f)

        project["root"] = str(root)
        return project

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
