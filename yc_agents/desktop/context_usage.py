import json
import os
from pathlib import Path

from yc_agents.desktop.documents import DocumentService
from yc_agents.desktop.sessions import SessionStore


DEFAULT_CONTEXT_WINDOW_TOKENS = 128000


class TokenCounter:
    def __init__(self, model=None):
        self.model = model or os.environ.get("LLM_MODEL_ID", "")
        self.encoding_name = "fallback"
        self.exact = False
        self._encoding = self._load_encoding()

    def count(self, text):
        if not text:
            return 0

        if self._encoding is not None:
            return len(self._encoding.encode(text))

        return len(text.split())

    def _load_encoding(self):
        try:
            import tiktoken
        except ImportError:
            return None

        try:
            encoding = tiktoken.encoding_for_model(self.model)
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")

        self.encoding_name = encoding.name
        self.exact = True
        return encoding


class ContextUsageService:
    def __init__(self, project_root, model=None, max_tokens=None):
        self.project_root = Path(project_root).resolve()
        self.counter = TokenCounter(model=model)
        self.max_tokens = max_tokens or int(
            os.environ.get("YC_AGENTS_CONTEXT_WINDOW_TOKENS")
            or os.environ.get("LLM_CONTEXT_WINDOW_TOKENS")
            or DEFAULT_CONTEXT_WINDOW_TOKENS
        )

    def for_session(self, session_id):
        session = SessionStore(self.project_root).get(session_id)
        messages_text = self._messages_text(session.get("messages", []))
        memory_text = self._memory_text()
        documents_text = DocumentService(self.project_root).build_context_summary()

        sections = {
            "messages": self.counter.count(messages_text),
            "memory": self.counter.count(memory_text),
            "documents": self.counter.count(documents_text),
        }
        used_tokens = sum(sections.values())

        return {
            "used_tokens": used_tokens,
            "max_tokens": self.max_tokens,
            "percent_used": round((used_tokens / self.max_tokens) * 100, 2)
            if self.max_tokens
            else 0,
            "tokenizer": self.counter.encoding_name,
            "exact": self.counter.exact,
            "sections": sections,
        }

    def _messages_text(self, messages):
        lines = []
        for message in messages:
            role = message.get("role", "assistant")
            content = message.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _memory_text(self):
        memory_dir = self.project_root / "memory"
        parts = []

        summary_path = memory_dir / "summary.md"
        if summary_path.exists():
            parts.append(summary_path.read_text(encoding="utf-8"))

        profile_path = memory_dir / "research_profile.json"
        if profile_path.exists():
            try:
                parts.append(json.dumps(json.loads(profile_path.read_text(encoding="utf-8")), ensure_ascii=False))
            except json.JSONDecodeError:
                parts.append(profile_path.read_text(encoding="utf-8"))

        return "\n".join(parts)
