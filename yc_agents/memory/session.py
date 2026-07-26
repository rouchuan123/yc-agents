import json
from pathlib import Path


def _parse_message_text(text):
    stripped = text.lstrip()
    if not stripped:
        return [], "empty"
    if stripped.startswith("["):
        return json.loads(text), "array"
    return (
        [json.loads(line) for line in text.splitlines() if line.strip()],
        "lines",
    )


def read_message_records(path, tail=None):
    # New sessions store one JSON message per line (messages.jsonl); legacy
    # sessions keep a JSON array (messages.json). Content sniffing keeps both
    # readable no matter which suffix the caller holds.
    path = Path(path)
    candidates = [path]
    if path.suffix == ".jsonl":
        candidates.append(path.with_suffix(".json"))

    messages = []
    for candidate in candidates:
        if candidate.exists():
            messages, _format = _parse_message_text(
                candidate.read_text(encoding="utf-8")
            )
            break

    if tail is not None and int(tail) > 0:
        messages = messages[-int(tail):]
    return messages


class SessionMemory:
    def __init__(self, file_path="data/memory/session.json", max_messages=None):
        self.file_path = Path(file_path)
        self.max_messages = max_messages
        self.messages = []
        self._synced_count = None

    def add_message(self, role, content):
        message = {
            "role": role,
            "content": content,
        }
        self.messages.append(message)
        self._trim()

    def add_structured_message(self, role, content, **metadata):
        message = {
            "role": role,
            "content": content,
        }
        for key, value in metadata.items():
            if value is not None:
                message[key] = value
        self.messages.append(message)
        self._trim()

    def get_messages(self):
        return list(self.messages)

    def load(self, tail=None):
        self._synced_count = None
        if not self._jsonl_mode():
            if not self.file_path.exists():
                self.messages = []
                return self.messages
            with self.file_path.open("r", encoding="utf-8") as f:
                self.messages = json.load(f)
            if tail is not None and int(tail) > 0:
                self.messages = self.messages[-int(tail):]
            self._trim()
            return self.messages

        self.messages = []
        if self.file_path.exists():
            self.messages, source_format = _parse_message_text(
                self.file_path.read_text(encoding="utf-8")
            )
            if source_format in ("lines", "empty"):
                # The file already holds every message up to this point, so
                # save() only has to append what gets added afterwards.
                self._synced_count = len(self.messages)
        else:
            legacy = self.file_path.with_suffix(".json")
            if legacy.exists():
                self.messages, _format = _parse_message_text(
                    legacy.read_text(encoding="utf-8")
                )
        if tail is not None and int(tail) > 0:
            dropped = len(self.messages) - int(tail)
            self.messages = self.messages[-int(tail):]
            if self._synced_count is not None and dropped > 0:
                self._synced_count = len(self.messages)
        self._trim()
        return self.messages

    def replace(self, messages):
        self.messages = list(messages or [])
        self._synced_count = None
        self._trim()
        return self.save()

    def _trim(self):
        if self.max_messages is not None and self.max_messages > 0:
            self.messages = self.messages[-self.max_messages:]

    def save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._jsonl_mode():
            with self.file_path.open("w", encoding="utf-8") as f:
                json.dump(self.messages, f, ensure_ascii=False, indent=2)
            return self.file_path

        synced = self._synced_count
        appendable = (
            synced is not None
            and synced <= len(self.messages)
            and self.max_messages is None
            and self.file_path.exists()
        )
        mode = "a" if appendable else "w"
        pending = self.messages[synced:] if appendable else self.messages
        with self.file_path.open(mode, encoding="utf-8") as f:
            for message in pending:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._synced_count = len(self.messages)

        legacy = self.file_path.with_suffix(".json")
        if legacy != self.file_path and legacy.exists():
            legacy.unlink()

        return self.file_path

    def _jsonl_mode(self):
        return self.file_path.suffix == ".jsonl"
