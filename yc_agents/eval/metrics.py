def keyword_success(output, expected_keywords):
    text = output or ""
    return all(keyword in text for keyword in expected_keywords)


def tool_success(trace_events, required_tools):
    called = {
        event.get("payload", {}).get("tool_name")
        for event in trace_events
        if event.get("event_type") == "tool_called"
    }
    return all(tool in called for tool in required_tools)


def trace_event_success(trace_events, expected_events):
    event_types = {event.get("event_type") for event in trace_events}
    return all(event_type in event_types for event_type in expected_events)


def forbidden_tool_success(trace_events, forbidden_tools):
    called = {
        event.get("payload", {}).get("tool_name")
        for event in trace_events
        if event.get("event_type") == "tool_called"
    }
    return not any(tool in called for tool in forbidden_tools)


TOOL_EVENT_BUCKETS = {
    "tool_called": "called",
    "tool_denied": "denied",
    "tool_validation_failed": "validation_failed",
    "tool_retry": "retry",
    "tool_failed": "failed",
    "tool_needs_approval": "approval_required",
}


def tool_event_counts(trace_events):
    counts = {
        "called": 0,
        "denied": 0,
        "validation_failed": 0,
        "retry": 0,
        "failed": 0,
        "approval_required": 0,
    }

    for event in trace_events:
        bucket = TOOL_EVENT_BUCKETS.get(event.get("event_type"))
        if bucket is not None:
            counts[bucket] += 1

    return counts


def classify_tool_events(trace_events):
    labels = []

    for event in trace_events:
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        error_type = payload.get("error_type")

        if event_type == "tool_denied":
            labels.append("policy_denial")
        elif event_type == "tool_validation_failed":
            labels.append("schema_validation")
        elif event_type == "tool_needs_approval":
            labels.append("approval_required")
        elif event_type == "tool_failed" and error_type == "timeout":
            labels.append("tool_timeout")
        elif event_type == "tool_failed":
            labels.append("tool_execution_error")
        elif event_type == "tool_retry":
            labels.append("retry")

    return labels


def retrieval_hit(results, reference_sources):
    result_sources = {item.get("source") for item in results}
    return any(source in result_sources for source in reference_sources)


def citation_precision(citations, reference_sources):
    if not citations:
        return 0

    reference_sources = set(reference_sources)
    hits = sum(1 for citation in citations if citation in reference_sources)
    return hits / len(citations)


def noise_resistance_score(results):
    results = list(results or [])
    if not results:
        return 0

    relevant = [
        item for item in results
        if item.get("metadata", {}).get("label") == "relevant"
    ]
    return len(relevant) / len(results)


def conflict_awareness_success(output, expects_conflict=False):
    if not expects_conflict:
        return True

    text = output or ""
    conflict_terms = ["冲突", "不一致", "矛盾", "分别说明", "来源不同"]
    return any(term in text for term in conflict_terms)


def verification_success(report):
    return bool(isinstance(report, dict) and report.get("passed") is True)


def average(values):
    values = list(values)
    if not values:
        return 0
    return sum(values) / len(values)
