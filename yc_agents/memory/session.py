import json
from pathlib import Path


class SessionMemory:
    def __init__(self, file_path="data/memory/session.json", max_messages=20):
        self.file_path = Path(file_path)
        self.max_messages = max_messages
        self.messages = []

    def add_message(self, role, content):
        message = {
            "role": role,
            "content": content,
        }
        self.messages.append(message)
        self.messages = self.messages[-self.max_messages:]

    def get_messages(self):
        return list(self.messages)

    def load(self):
        if not self.file_path.exists():
            self.messages = []
            return self.messages

        with self.file_path.open("r", encoding="utf-8") as f:
            self.messages = json.load(f)

        self.messages = self.messages[-self.max_messages:]
        return self.messages

    def save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(self.messages, f, ensure_ascii=False, indent=2)

        return self.file_path