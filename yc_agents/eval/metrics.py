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


def retrieval_hit(results, reference_sources):
    result_sources = {item.get("source") for item in results}
    return any(source in result_sources for source in reference_sources)


def citation_precision(citations, reference_sources):
    if not citations:
        return 0

    reference_sources = set(reference_sources)
    hits = sum(1 for citation in citations if citation in reference_sources)
    return hits / len(citations)


def average(values):
    values = list(values)
    if not values:
        return 0
    return sum(values) / len(values)
