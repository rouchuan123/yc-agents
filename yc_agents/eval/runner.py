import argparse
import json
import time
from pathlib import Path

from main import build_runtime
from yc_agents.eval.case import load_cases
from yc_agents.eval.metrics import keyword_success


def run_cases(runtime, cases):
    results = []

    for case in cases:
        started_at = time.perf_counter()
        output = runtime.run(case.input)
        latency_seconds = time.perf_counter() - started_at

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
