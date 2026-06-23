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

    def is_over_budget(self):
        return self.total_estimated_tokens >= self.max_tokens

    def breakdown(self):
        return dict(self.sections)
