class ContextManager:
    def build_skill_selection_context(self, user_input, skills):
        return {
            "task": "skill_selection",
            "user_input": user_input,
            "skills": [
                self._summarize_skill(skill)
                for skill in skills
            ],
        }

    def _summarize_skill(self, skill):
        return {
            "name": skill.name,
            "description": skill.description,
            "allowed_tools": skill.allowed_tools,
        }