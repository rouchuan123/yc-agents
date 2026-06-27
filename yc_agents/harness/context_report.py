import json

from yc_agents.harness.token_budget import TokenBudget


def _serialize(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def build_context_report(context, max_tokens=8000):
    budget = TokenBudget(max_tokens=max_tokens)
    sections = {}

    for name in ["user_input", "memory", "workspace", "skills", "selected_skill", "rag_results"]:
        if name not in context:
            continue

        serialized = _serialize(context[name])
        budget.add(name, serialized)
        sections[name] = {
            "estimated_tokens": budget.sections[name],
            "present": True,
        }

    return {
        "max_tokens": budget.max_tokens,
        "total_estimated_tokens": budget.total_estimated_tokens,
        "over_budget": budget.is_over_budget(),
        "sections": sections,
    }
