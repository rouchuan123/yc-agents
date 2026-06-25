from yc_agents.prompts.builder import PromptBuilder


class SkillAgent:
    def __init__(self, llm, prompt_builder=None):
        self.llm = llm
        self.prompt_builder = prompt_builder or PromptBuilder()

    def select_skill(self, context):
        return self.llm.think(
            self.prompt_builder.skill_selection_messages(context)
        )
