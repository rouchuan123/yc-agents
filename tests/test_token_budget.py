from yc_agents.harness.token_budget import TokenBudget


def test_token_budget_estimates_text_and_flags_over_budget():
    budget = TokenBudget(max_tokens=10)

    budget.add("memory", "a " * 20)

    assert budget.total_estimated_tokens > 0
    assert budget.is_over_budget()


def test_token_budget_breakdown():
    budget = TokenBudget(max_tokens=100)
    budget.add("skill_summary", "abc")

    assert budget.breakdown()["skill_summary"] > 0


def test_token_budget_tracks_sections_and_remaining_tokens():
    budget = TokenBudget(max_tokens=10)
    budget.add("memory", "abcdefgh")
    budget.add("memory", "ijkl")
    budget.add("skills", "mnop")

    assert budget.breakdown()["memory"] == 3
    assert budget.breakdown()["skills"] == 1
    assert budget.remaining_tokens == 6
    assert budget.is_over_budget() is False


def test_token_budget_marks_exact_limit_as_over_budget():
    budget = TokenBudget(max_tokens=1)
    budget.add("input", "abcd")

    assert budget.remaining_tokens == 0
    assert budget.is_over_budget() is True
