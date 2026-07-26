SOFT_BUDGET_NOTICE = (
    "系统提示：本次运行 token 预算将尽，请收敛到最少步骤完成任务，"
    "或直接给出最终答案，不要再扩大调用范围。"
)


class TokenBudgetPolicy:
    """run 级成本熔断：软限提醒收敛，硬限优雅停止。None 表示不启用。"""

    def __init__(self, soft_limit_tokens=None, hard_limit_tokens=None):
        self.soft_limit_tokens = self._normalize(soft_limit_tokens)
        self.hard_limit_tokens = self._normalize(hard_limit_tokens)

    @staticmethod
    def _normalize(value):
        if value in (None, ""):
            return None
        tokens = int(value)
        return tokens if tokens > 0 else None

    @property
    def enabled(self):
        return (
            self.soft_limit_tokens is not None
            or self.hard_limit_tokens is not None
        )

    @classmethod
    def from_runtime_config(cls, runtime_config):
        budget = dict((runtime_config or {}).get("tokenBudget") or {})
        return cls(
            soft_limit_tokens=budget.get("softTokens"),
            hard_limit_tokens=budget.get("hardTokens"),
        )

    def start_meter(self, usage_ledger):
        # ledger 不可用时静默禁用：预算门是保险丝，不应反过来打断运行。
        if not self.enabled or usage_ledger is None:
            return None
        if getattr(usage_ledger, "session_totals", None) is None:
            return None
        return TokenBudgetMeter(self, usage_ledger)


class TokenBudgetMeter:
    """以 run 开始时的会话累计为基线，度量本次 run 的 token 增量。"""

    def __init__(self, policy, usage_ledger):
        self.policy = policy
        self.usage_ledger = usage_ledger
        self.baseline_tokens = self._session_tokens()
        self.soft_notified = False

    def _session_tokens(self):
        totals = getattr(self.usage_ledger, "session_totals", None)
        return int(getattr(totals, "total_tokens", 0) or 0)

    @property
    def run_tokens(self):
        return max(0, self._session_tokens() - self.baseline_tokens)

    def soft_notice(self):
        return SOFT_BUDGET_NOTICE

    def check(self):
        tokens = self.run_tokens
        hard = self.policy.hard_limit_tokens
        if hard is not None and tokens >= hard:
            return {"level": "hard", "run_tokens": tokens, "limit": hard}
        soft = self.policy.soft_limit_tokens
        if soft is not None and tokens >= soft and not self.soft_notified:
            self.soft_notified = True
            return {"level": "soft", "run_tokens": tokens, "limit": soft}
        return None


class TokenBudget:
    def __init__(self, max_tokens=8000):
        self.max_tokens = max_tokens
        self.sections = {}

    def estimate(self, text):
        return max(1, len(text) // 4) if text else 0

    def add(self, name, text):
        self.sections[name] = self.sections.get(name, 0) + self.estimate(text)

    @property
    def total_estimated_tokens(self):
        return sum(self.sections.values())

    @property
    def remaining_tokens(self):
        return max(0, self.max_tokens - self.total_estimated_tokens)

    def is_over_budget(self):
        return self.total_estimated_tokens >= self.max_tokens

    def breakdown(self):
        return dict(self.sections)
