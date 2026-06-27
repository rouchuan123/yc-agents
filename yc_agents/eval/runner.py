import argparse
import json
import time
from pathlib import Path

from main import build_runtime
from yc_agents.eval.case import load_cases
from yc_agents.eval.metrics import (
    classify_tool_events,
    conflict_awareness_success,
    forbidden_tool_success,
    keyword_success,
    noise_resistance_score,
    retrieval_hit,
    tool_success,
    tool_event_counts,
    trace_event_success,
)


def _extract_latest_rag_result(trace_events):
    for event in reversed(trace_events):
        payload = event.get("payload", {})
        if payload.get("tool_name") != "rag_search":
            continue

        result = payload.get("result")
        if isinstance(result, dict) and result.get("type") == "rag_search_result":
            return result

    return {"results": [], "sources": []}


def run_cases(runtime, cases):
    results = []

    for case in cases:
        started_at = time.perf_counter()
        output = runtime.run(case.input)
        latency_seconds = time.perf_counter() - started_at
        trace_events = list(getattr(runtime, "last_trace_events", []))
        rag_result = _extract_latest_rag_result(trace_events)
        rag_results = rag_result.get("results", [])
        noise_score = noise_resistance_score(rag_results)

        results.append(
            {
                "case_id": case.id,
                "category": case.category,
                "input": case.input,
                "output": output,
                "keyword_success": keyword_success(output, case.expected_keywords),
                "latency_seconds": latency_seconds,
                "required_tools": case.required_tools,
                "reference_sources": case.reference_sources,
                "trace_events": trace_events,
                "tool_success": tool_success(trace_events, case.required_tools),
                "trace_event_success": trace_event_success(
                    trace_events,
                    case.expected_trace_events,
                ),
                "forbidden_tool_success": forbidden_tool_success(
                    trace_events,
                    case.forbidden_tools,
                ),
                "tool_event_counts": tool_event_counts(trace_events),
                "tool_failure_labels": classify_tool_events(trace_events),
                "retrieval_hit": retrieval_hit(rag_results, case.reference_sources),
                "noise_resistance_score": noise_score,
                "noise_resistance_success": noise_score >= case.min_noise_resistance,
                "conflict_awareness_success": conflict_awareness_success(
                    output,
                    expects_conflict=case.expects_conflict,
                ),
            }
        )

    return results


def save_results(results, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    cases = load_cases(args.cases)
    runtime = build_runtime()
    results = run_cases(runtime, cases)
    save_results(results, args.output)
    print(f"Saved {len(results)} evaluation results to {args.output}")


if __name__ == "__main__":
    main()
