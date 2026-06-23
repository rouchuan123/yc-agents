from yc_agents.eval.metrics import average


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

    return {
        "case_count": case_count,
        "task_success_rate": successes / case_count,
        "avg_latency_seconds": average(latencies),
    }
