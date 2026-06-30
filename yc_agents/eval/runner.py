import argparse
import json
import time
from pathlib import Path

from main import build_runtime
from yc_agents.eval.case import load_cases
from yc_agents.eval.metrics import (
    classify_tool_events,
    conflict_awareness_success,
    expected_verification_success,
    forbidden_tool_success,
    keyword_success,
    noise_resistance_score,
    output_sections_success,
    retrieval_hit,
    skill_success,
    state_steps_success,
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


def _load_state(runtime):
    run_dir = getattr(runtime, "last_run_dir", None)
    if run_dir is None:
        return None

    state_path = Path(run_dir) / "state.json"
    if not state_path.exists():
        return None

    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run_cases(runtime, cases):
    results = []

    for case in cases:
        started_at = time.perf_counter()
        output = runtime.run(case.input)
        latency_seconds = time.perf_counter() - started_at
        trace_events = list(getattr(runtime, "last_trace_events", []))
        state = _load_state(runtime)
        rag_result = _extract_latest_rag_result(trace_events)
        rag_results = rag_result.get("results", [])
        noise_score = noise_resistance_score(rag_results)

        result = {
            "case_id": case.id,
            "category": case.category,
            "judge_mode": case.judge_mode,
            "input": case.input,
            "output": output,
            "expected_skill": case.expected_skill,
            "failure_notes": case.failure_notes,
            "keyword_success": keyword_success(output, case.expected_keywords),
            "output_sections_success": output_sections_success(
                output,
                case.expected_output_sections,
            ),
            "latency_seconds": latency_seconds,
            "required_tools": case.required_tools,
            "reference_sources": case.reference_sources,
            "trace_events": trace_events,
            "skill_success": skill_success(trace_events, case.expected_skill),
            "tool_success": tool_success(trace_events, case.required_tools),
            "trace_event_success": trace_event_success(
                trace_events,
                case.expected_trace_events,
            ),
            "state_steps_success": state_steps_success(
                state,
                case.expected_state_steps,
            ),
            "verification_success": expected_verification_success(
                state,
                case.expected_verification,
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
            "run_id": getattr(runtime, "last_run_id", None),
        }
        results.append(result)

        analytics_recorder = getattr(runtime, "analytics_recorder", None)
        if analytics_recorder is not None:
            analytics_recorder.record_eval_result(result)

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
