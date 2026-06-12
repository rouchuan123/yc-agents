from yc_agents.skills.definition import SkillDefinition


class SkillRegistry:
    def __init__(self):
        self.skills = {}

    def register(self, skill):
        if not isinstance(skill, SkillDefinition):
            raise TypeError("skill must be a SkillDefinition")

        if not skill.name:
            raise ValueError("skill.name is required")

        if skill.name in self.skills:
            raise ValueError(f"Skill already registered: {skill.name}")

        self.skills[skill.name] = skill
        return skill

    def get_skill(self, name):
        if name not in self.skills:
            raise KeyError(f"Skill not registered: {name}")

        return self.skills[name]

    def list_skills(self):
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "allowed_tools": skill.allowed_tools,
            }
            for skill in self.skills.values()
        ]