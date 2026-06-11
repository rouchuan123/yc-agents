import json
from pathlib import Path


class ResearchProfileMemory:
    def __init__(self, file_path="data/memory/research_profile.json"):
        self.file_path = Path(file_path)
        self.profile = self.default_profile()

    def default_profile(self):
        return {
            "major": "",
            "research_direction": "",
            "thesis_type": "",
            "tech_stack": [],
            "current_topic": "",
            "advisor_feedback": [],
            "literature_findings": [],
            "system_ideas": [],
        }

    def load(self):
        if not self.file_path.exists():
            return self.profile

        with self.file_path.open("r", encoding="utf-8") as f:
            self.profile = json.load(f)

        return self.profile

    def save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(self.profile, f, ensure_ascii=False, indent=2)

        return self.file_path

    def update_field(self, key, value):
        if key not in self.profile:
            raise KeyError(f"Unknown profile field: {key}")

        self.profile[key] = value
        return self.profile

    def get_profile(self):
        return dict(self.profile)