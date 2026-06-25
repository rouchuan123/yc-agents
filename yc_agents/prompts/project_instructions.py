from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectInstruction:
    source: str
    path: Path | None
    content: str


class ProjectInstructionLoader:
    def __init__(self, workspace_root):
        self.workspace_root = Path(workspace_root)

    def load(self):
        instructions = []

        for source, path in self._instruction_paths():
            if not path.exists() or not path.is_file():
                continue

            content = path.read_text(encoding="utf-8").strip()
            if not content:
                continue

            instructions.append(
                ProjectInstruction(
                    source=source,
                    path=path,
                    content=content,
                )
            )

        return instructions

    def _instruction_paths(self):
        return [
            ("YCORE.md", self.workspace_root / "YCORE.md"),
            (".ycore/YCORE.md", self.workspace_root / ".ycore" / "YCORE.md"),
        ]
