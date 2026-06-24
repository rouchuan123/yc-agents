from pathlib import Path

import yaml

from yc_agents.skills.definition import SkillDefinition


class SkillLoader:
    def __init__(self, skills_dir="skills"):
        self.skills_dir = Path(skills_dir)

    def load_all(self):
        if not self.skills_dir.exists():
            return []

        skills = []

        for skill_dir in sorted(self.skills_dir.iterdir()):
            skill_file = skill_dir / "SKILL.md"

            if not skill_dir.is_dir():
                continue

            if not skill_file.exists():
                continue

            skills.append(self.load_one(skill_dir))

        return skills

    def load_one(self, skill_dir):
        skill_path = Path(skill_dir)
        skill_file = skill_path / "SKILL.md"

        if not skill_file.exists():
            raise FileNotFoundError(f"Skill file not found: {skill_file}")

        text = skill_file.read_text(encoding="utf-8")
        metadata, body = self._split_front_matter(text)

        name = metadata.get("name")
        description = metadata.get("description", "")
        allowed_tools = metadata.get("allowed_tools", [])
        triggers = metadata.get("triggers", [])
        inputs = metadata.get("inputs", [])
        outputs = metadata.get("outputs", [])
        examples = metadata.get("examples", [])

        if not name:
            raise ValueError(f"Skill name is required: {skill_file}")

        if allowed_tools is None:
            allowed_tools = []

        return SkillDefinition(
            name=name,
            description=description,
            allowed_tools=list(allowed_tools),
            triggers=list(triggers or []),
            inputs=list(inputs or []),
            outputs=list(outputs or []),
            examples=list(examples or []),
            body=body.strip(),
            path=str(skill_path).replace("\\", "/"),
            scripts=self._discover_scripts(skill_path / "scripts"),
            assets=self._discover_files(skill_path / "assets"),
            references=self._discover_files(skill_path / "references"),
        )

    def _split_front_matter(self, text):
        if not text.startswith("---"):
            raise ValueError("SKILL.md must start with YAML front matter")

        parts = text.split("---", 2)

        if len(parts) < 3:
            raise ValueError("SKILL.md front matter is not closed")

        metadata = yaml.safe_load(parts[1]) or {}

        if not isinstance(metadata, dict):
            raise ValueError("SKILL.md front matter must be a YAML mapping")

        return metadata, parts[2]

    def _discover_files(self, directory):
        if not directory.exists():
            return []

        return [
            str(path).replace("\\", "/")
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        ]

    def _discover_scripts(self, directory):
        scripts = []

        for path in self._discover_files(directory):
            scripts.append(
                {
                    "path": path,
                    "executable_candidate": path.endswith(".py"),
                }
            )

        return scripts
