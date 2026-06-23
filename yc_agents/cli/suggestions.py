from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSuggestion:
    command: str
    description: str


DEFAULT_SUGGESTIONS = [
    CommandSuggestion("/session", "切换会话"),
    CommandSuggestion("/session new", "新建会话"),
    CommandSuggestion("/session delete", "删除会话"),
    CommandSuggestion("/workspace", "切换工作区"),
    CommandSuggestion("/workspace add", "添加工作区"),
    CommandSuggestion("/workspace current", "当前工作区"),
    CommandSuggestion("/workspace delete", "删除工作区"),
    CommandSuggestion("/status", "查看状态"),
    CommandSuggestion("/clear", "清空屏幕"),
    CommandSuggestion("/exit", "退出"),
]


class CommandSuggestionRegistry:
    def __init__(self, suggestions=None):
        self.suggestions = list(suggestions or DEFAULT_SUGGESTIONS)

    def filter(self, text):
        query = (text or "").strip().lower()
        if not query or query == "/":
            return list(self.suggestions)

        return [
            suggestion
            for suggestion in self.suggestions
            if suggestion.command.lower().startswith(query)
        ]
