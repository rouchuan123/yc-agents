import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yc_agents.eval.case import EvalCase
from yc_agents.eval.runner import run_cases


class DemoRuntime:
    def __init__(self):
        self.last_trace_events = []

    def run(self, user_input):
        if "仓库" in user_input or "架构" in user_input or "测试" in user_input:
            self.last_trace_events = [
                {"event_type": "tool_called", "payload": {"tool_name": "workspace_files"}}
            ]
            return "架构 风险 测试 文件证据 已生成"

        self.last_trace_events = [
            {"event_type": "skill_selected", "payload": {"selected_skill": "eval-writer"}}
        ]
        return "deterministic eval rubric trace 方案 已生成"


def demo_cases():
    return [
        EvalCase(
            id="demo-code-review-001",
            category="project_audit",
            input="请审查当前仓库的架构风险和测试缺口。",
            expected_keywords=["架构", "测试"],
            required_tools=["workspace_files"],
            expected_trace_events=["tool_called"],
        ),
        EvalCase(
            id="demo-eval-writer-001",
            category="eval_design",
            input="请为这个 code agent 设计 deterministic eval 和人工 rubric。",
            expected_keywords=["deterministic", "rubric"],
            expected_trace_events=["skill_selected"],
        ),
    ]


def run_demo_eval(output_path="outputs/eval/demo-results.json"):
    results = run_cases(DemoRuntime(), demo_cases())
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results


if __name__ == "__main__":
    output = run_demo_eval()
    print(f"Saved {len(output)} demo eval results to outputs/eval/demo-results.json")
