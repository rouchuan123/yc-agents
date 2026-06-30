import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class EvalCase:
    id: str
    category: str
    input: str
    judge_mode: str = "deterministic"
    expected_skill: str | None = None
    expected_keywords: list[str] = field(default_factory=list)
    expected_output_sections: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    reference_sources: list[str] = field(default_factory=list)
    expected_trace_events: list[str] = field(default_factory=list)
    expected_state_steps: list[str] = field(default_factory=list)
    expected_verification: bool | None = None
    forbidden_tools: list[str] = field(default_factory=list)
    expects_conflict: bool = False
    min_noise_resistance: float = 0.0
    failure_notes: str = ""


def load_cases(path):
    cases = []
    path = Path(path)

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            data = json.loads(line)
            cases.append(
                EvalCase(
                    id=data["id"],
                    category=data["category"],
                    input=data["input"],
                    judge_mode=data.get("judge_mode", "deterministic"),
                    expected_skill=data.get("expected_skill"),
                    expected_keywords=list(data.get("expected_keywords", [])),
                    expected_output_sections=list(
                        data.get("expected_output_sections", [])
                    ),
                    required_tools=list(data.get("required_tools", [])),
                    reference_sources=list(data.get("reference_sources", [])),
                    expected_trace_events=list(data.get("expected_trace_events", [])),
                    expected_state_steps=list(data.get("expected_state_steps", [])),
                    expected_verification=data.get("expected_verification"),
                    forbidden_tools=list(data.get("forbidden_tools", [])),
                    expects_conflict=bool(data.get("expects_conflict", False)),
                    min_noise_resistance=float(data.get("min_noise_resistance", 0.0)),
                    failure_notes=data.get("failure_notes", ""),
                )
            )

    return cases
