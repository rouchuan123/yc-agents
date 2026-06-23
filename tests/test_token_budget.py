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
