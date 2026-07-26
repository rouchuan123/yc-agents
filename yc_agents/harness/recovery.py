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
    lifetime_max_attempts: int = 20

    @classmethod
    def from_runtime_config(cls, runtime_config):
        config = dict(runtime_config or {})
        return cls(
            protocol_retries=int(config.get("invalidJsonRetryCount", 2)),
            provider_retries=int(config.get("providerRetryCount", 1)),
            verification_retries=int(config.get("verificationRetryCount", 1)),
            max_attempts=int(config.get("maxRecoveryAttempts", 4)),
            provider_backoff_seconds=float(
                config.get("providerRetryBackoffSeconds", 1)
            ),
            lifetime_max_attempts=int(
                config.get("maxLifetimeRecoveryAttempts", 20)
            ),
        )


@dataclass
class RecoveryController:
    policy: RecoveryPolicy
    total_attempts: int = 0
    lifetime_attempts: int = 0
    attempts: dict[str, int] = field(default_factory=dict)

    def reserve(self, kind):
        limit = self._limit_for(kind)
        used = self.attempts.get(kind, 0)
        if self.lifetime_exhausted():
            return None
        if used >= limit or self.total_attempts >= self.policy.max_attempts:
            return None

        attempt = used + 1
        self.attempts[kind] = attempt
        self.total_attempts += 1
        self.lifetime_attempts += 1
        return {
            "kind": kind,
            "attempt": attempt,
            "limit": limit,
            "total_attempt": self.total_attempts,
            "total_limit": self.policy.max_attempts,
            "lifetime_attempt": self.lifetime_attempts,
            "lifetime_limit": self.policy.lifetime_max_attempts,
        }

    def snapshot(self):
        return {
            "total_attempts": self.total_attempts,
            "max_attempts": self.policy.max_attempts,
            "lifetime_attempts": self.lifetime_attempts,
            "lifetime_max_attempts": self.policy.lifetime_max_attempts,
            "attempts": dict(self.attempts),
        }

    def record_success(self, kind=None):
        """A successful recovery breaks the failure streak: clear that kind's
        counter and the global consecutive counter so max_attempts limits
        consecutive failures. The lifetime counter is never reset."""
        if kind is not None:
            self.attempts.pop(str(kind), None)
        self.total_attempts = 0

    def lifetime_exhausted(self):
        return self.lifetime_attempts >= max(
            0, int(self.policy.lifetime_max_attempts)
        )

    def reset(self, kind=None):
        """Reset recovered attempts so the global limit applies to consecutive failures."""
        if kind is None:
            self.total_attempts = 0
            self.attempts.clear()
            return
        released = self.attempts.pop(str(kind), 0)
        self.total_attempts = max(0, self.total_attempts - released)

    def _limit_for(self, kind):
        limits = {
            "protocol": self.policy.protocol_retries,
            "provider": self.policy.provider_retries,
            "verification": self.policy.verification_retries,
            "tool_feedback": self.policy.max_attempts,
        }
        return max(0, int(limits.get(kind, 0)))
