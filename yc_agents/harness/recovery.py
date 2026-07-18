from dataclasses import dataclass, field


class RunStoppedError(RuntimeError):
    def __init__(self, message, *, kind, stage, error_type, exhausted=False):
        super().__init__(message)
        self.kind = kind
        self.stage = stage
        self.error_type = error_type
        self.exhausted = bool(exhausted)


@dataclass(frozen=True)
class RecoveryPolicy:
    protocol_retries: int = 2
    provider_retries: int = 1
    verification_retries: int = 1
    max_attempts: int = 4
    provider_backoff_seconds: float = 1.0


@dataclass
class RecoveryController:
    policy: RecoveryPolicy
    total_attempts: int = 0
    attempts: dict[str, int] = field(default_factory=dict)

    def reserve(self, kind):
        limit = self._limit_for(kind)
        used = self.attempts.get(kind, 0)
        if used >= limit or self.total_attempts >= self.policy.max_attempts:
            return None

        attempt = used + 1
        self.attempts[kind] = attempt
        self.total_attempts += 1
        return {
            "kind": kind,
            "attempt": attempt,
            "limit": limit,
            "total_attempt": self.total_attempts,
            "total_limit": self.policy.max_attempts,
        }

    def snapshot(self):
        return {
            "total_attempts": self.total_attempts,
            "max_attempts": self.policy.max_attempts,
            "attempts": dict(self.attempts),
        }

    def _limit_for(self, kind):
        limits = {
            "protocol": self.policy.protocol_retries,
            "provider": self.policy.provider_retries,
            "verification": self.policy.verification_retries,
            "tool_feedback": self.policy.max_attempts,
        }
        return max(0, int(limits.get(kind, 0)))
