from yc_agents.prompts.builder import PromptBuilder
from yc_agents.core.llm_call import invoke_llm


class SkillAgent:
    def __init__(self, llm, prompt_builder=None):
        self.llm = llm
        self.prompt_builder = prompt_builder or PromptBuilder()

    def select_skill(self, context):
        messages = self.prompt_builder.skill_selection_messages(context)
        think_json = getattr(self.llm, "think_json", None)
        if callable(think_json):
            return invoke_llm(think_json, messages, usage_kind="auxiliary")
        return invoke_llm(self.llm.think, messages, usage_kind="auxiliary")
