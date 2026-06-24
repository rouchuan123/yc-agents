from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSuggestion:
    command: str
    description: str
    completion: str | None = None


DEFAULT_SUGGESTIONS = [
    CommandSuggestion("/session", "切换会话"),
    CommandSuggestion("/session new", "新建会话"),
    CommandSuggestion("/session new <title>", "新建指定标题的会话", "/session new "),
    CommandSuggestion("/session session_id", "切换到指定会话"),
    CommandSuggestion("/session delete", "删除当前会话"),
    CommandSuggestion("/session delete session_id", "删除指定会话", "/session delete "),
    CommandSuggestion("/workspace", "切换工作区"),
    CommandSuggestion("/workspace add <path>", "添加工作区", "/workspace add "),
    CommandSuggestion("/workspace workspace_id", "切换到指定工作区"),
    CommandSuggestion("/workspace current", "当前工作区"),
    CommandSuggestion("/workspace delete", "删除工作区"),
    CommandSuggestion("/workspace delete <path-or-id>", "删除指定工作区状态", "/workspace delete "),
    CommandSuggestion("/status", "查看状态"),
    CommandSuggestion("/stop", "停止当前运行"),
    CommandSuggestion("/skills", "查看可用技能"),
    CommandSuggestion("/clear", "清空屏幕"),
    CommandSuggestion("/confirm", "确认待执行操作"),
    CommandSuggestion("/cancel", "取消待执行操作"),
    CommandSuggestion("/exit", "退出"),
    CommandSuggestion("/quit", "退出"),
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
