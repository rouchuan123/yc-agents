import json
import subprocess
import sys

from scripts.demo_eval_run import run_demo_eval


def test_demo_eval_run_writes_results(tmp_path):
    output_path = tmp_path / "demo-results.json"

    results = run_demo_eval(output_path=output_path)

    assert output_path.exists()
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == results
    assert len(results) >= 2
    assert all("case_id" in item for item in results)


def test_demo_eval_run_uses_code_agent_cases(tmp_path):
    output_path = tmp_path / "demo-results.json"

    results = run_demo_eval(output_path=output_path)

    categories = {result["category"] for result in results}
    outputs = "\n".join(result["output"] for result in results)
    assert {"project_audit", "eval_design"}.issubset(categories)
    assert ("论文") not in outputs
    assert ("开题") not in outputs


def test_demo_eval_run_script_executes_from_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/demo_eval_run.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Saved 2 demo eval results" in completed.stdout
