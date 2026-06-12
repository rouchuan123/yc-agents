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

        if not name:
            raise ValueError(f"Skill name is required: {skill_file}")

        if allowed_tools is None:
            allowed_tools = []

        return SkillDefinition(
            name=name,
            description=description,
            allowed_tools=list(allowed_tools),
            body=body.strip(),
            path=str(skill_path).replace("\\", "/"),
        )

    def _split_front_matter(self, text):
        if not text.startswith("---"):
            raise ValueError("SKILL.md must start with YAML front matter")

        parts = text.split("---", 2)

        if len(parts) < 3:
            raise ValueError("SKILL.md front matter is not closed")

        metadata_text = parts[1]
        body = parts[2]

        metadata = yaml.safe_load(metadata_text) or {}

        if not isinstance(metadata, dict):
            raise ValueError("SKILL.md front matter must be a YAML mapping")

        return metadata, body