from yc_agents.eval.metrics import average


def _sum_tool_event_counts(results):
    totals = {
        "called": 0,
        "denied": 0,
        "validation_failed": 0,
        "retry": 0,
        "failed": 0,
        "approval_required": 0,
    }

    for result in results:
        counts = result.get("tool_event_counts", {})
        for key in totals:
            totals[key] += counts.get(key, 0)

    return totals


def _count_labels(results):
    labels = {}
    for result in results:
        for label in result.get("tool_failure_labels", []):
            labels[label] = labels.get(label, 0) + 1
    return labels


def summarize_results(results):
    results = list(results)
    case_count = len(results)

    if case_count == 0:
        return {
            "case_count": 0,
            "task_success_rate": 0,
            "avg_latency_seconds": 0,
        }

    successes = sum(1 for result in results if result.get("keyword_success"))
    latencies = [result.get("latency_seconds", 0) for result in results]
    tool_successes = [result.get("tool_success", True) for result in results]
    trace_successes = [result.get("trace_event_success", True) for result in results]
    forbidden_successes = [
        result.get("forbidden_tool_success", True) for result in results
    ]

    return {
        "case_count": case_count,
        "task_success_rate": successes / case_count,
        "tool_success_rate": average(1 if value else 0 for value in tool_successes),
        "trace_event_success_rate": average(
            1 if value else 0 for value in trace_successes
        ),
        "forbidden_tool_success_rate": average(
            1 if value else 0 for value in forbidden_successes
        ),
        "avg_latency_seconds": average(latencies),
        "tool_event_totals": _sum_tool_event_counts(results),
        "tool_failure_labels": _count_labels(results),
    }
