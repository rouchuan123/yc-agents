from yc_agents.prompts.builder import PromptBuilder


class SkillAgent:
    def __init__(self, llm, prompt_builder=None):
        self.llm = llm
        self.prompt_builder = prompt_builder or PromptBuilder()

    def select_skill(self, context):
        messages = self.prompt_builder.skill_selection_messages(context)
        think_json = getattr(self.llm, "think_json", None)
        if callable(think_json):
            return think_json(messages)
        return self.llm.think(messages)
