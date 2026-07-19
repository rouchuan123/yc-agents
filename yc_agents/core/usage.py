import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _value(source, *names, default=0):
    for name in names:
        if isinstance(source, dict) and name in source:
            return source[name]
        value = getattr(source, name, None)
        if value is not None:
            return value
    return default


def _nested_value(source, parent_names, child_names):
    parent = _value(source, *parent_names, default=None)
    if parent is None:
        return 0
    return _value(parent, *child_names, default=0)


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0

    @classmethod
    def from_provider(cls, usage):
        if usage is None:
            return None
        input_tokens = int(_value(usage, "prompt_tokens", "input_tokens", default=0) or 0)
        output_tokens = int(
            _value(usage, "completion_tokens", "output_tokens", default=0) or 0
        )
        total_tokens = int(_value(usage, "total_tokens", default=0) or 0)
        cached_tokens = int(
            _nested_value(
                usage,
                ("prompt_tokens_details", "input_tokens_details"),
                ("cached_tokens",),
            )
            or _value(usage, "cached_tokens", "cached_prompt_tokens", default=0)
            or 0
        )
        reasoning_tokens = int(
            _nested_value(
                usage,
                ("completion_tokens_details", "output_tokens_details"),
                ("reasoning_tokens",),
            )
            or _value(usage, "reasoning_tokens", default=0)
            or 0
        )
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens
        if total_tokens <= 0 and input_tokens <= 0 and output_tokens <= 0:
            return None
        return cls(
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            total_tokens=max(0, total_tokens),
            cached_tokens=max(0, cached_tokens),
            reasoning_tokens=max(0, reasoning_tokens),
        )

    @classmethod
    def estimated(cls, messages, output_text=""):
        serialized = json.dumps(messages or [], ensure_ascii=False, sort_keys=True)
        input_tokens = max(1, len(serialized) // 4) if serialized else 0
        output_text = str(output_text or "")
        output_tokens = max(1, len(output_text) // 4) if output_text else 0
        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    def add(self, other):
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.cached_tokens += other.cached_tokens
        self.reasoning_tokens += other.reasoning_tokens


@dataclass
class UsageSnapshot:
    usage: TokenUsage
    model: str
    call_kind: str = "primary"
    source: str = "provider"
    updated_at: str = field(default_factory=_now_iso)

    @property
    def total_tokens(self):
        return self.usage.total_tokens


class UsageLedger:
    def __init__(self, file_path=None):
        self.file_path = Path(file_path) if file_path else None
        self.current_context = None
        self.session_totals = TokenUsage()
        self.primary_calls = 0
        self.auxiliary_calls = 0
        self._lock = threading.RLock()
        self.load()

    def set_file_path(self, file_path, load=True):
        with self._lock:
            self.file_path = Path(file_path) if file_path else None
            self._reset()
            if load:
                self.load()

    def record(self, usage, model, call_kind="primary", source="provider"):
        normalized_kind = "auxiliary" if call_kind == "auxiliary" else "primary"
        snapshot = UsageSnapshot(
            usage=usage,
            model=str(model or "unknown"),
            call_kind=normalized_kind,
            source=str(source or "estimated"),
        )
        with self._lock:
            self.session_totals.add(usage)
            if normalized_kind == "primary":
                self.primary_calls += 1
                self.current_context = snapshot
            else:
                self.auxiliary_calls += 1
            self.save()
        return snapshot

    def to_dict(self):
        with self._lock:
            return {
                "version": 1,
                "current_context": self._snapshot_dict(self.current_context),
                "session_totals": asdict(self.session_totals),
                "primary_calls": self.primary_calls,
                "auxiliary_calls": self.auxiliary_calls,
            }

    def load(self):
        with self._lock:
            if self.file_path is None or not self.file_path.exists():
                return self
            try:
                data = json.loads(self.file_path.read_text(encoding="utf-8"))
                self.session_totals = TokenUsage(**dict(data.get("session_totals") or {}))
                self.primary_calls = max(0, int(data.get("primary_calls", 0)))
                self.auxiliary_calls = max(0, int(data.get("auxiliary_calls", 0)))
                current = data.get("current_context")
                if current:
                    self.current_context = UsageSnapshot(
                        usage=TokenUsage(**dict(current.get("usage") or {})),
                        model=str(current.get("model") or "unknown"),
                        call_kind=str(current.get("call_kind") or "primary"),
                        source=str(current.get("source") or "estimated"),
                        updated_at=str(current.get("updated_at") or _now_iso()),
                    )
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                self._reset()
        return self

    def _reset(self):
        self.current_context = None
        self.session_totals = TokenUsage()
        self.primary_calls = 0
        self.auxiliary_calls = 0

    def save(self):
        with self._lock:
            if self.file_path is None:
                return None
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
            temp_path.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp_path, self.file_path)
            return self.file_path

    @staticmethod
    def _snapshot_dict(snapshot):
        if snapshot is None:
            return None
        return {
            "usage": asdict(snapshot.usage),
            "model": snapshot.model,
            "call_kind": snapshot.call_kind,
            "source": snapshot.source,
            "updated_at": snapshot.updated_at,
        }
