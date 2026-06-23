import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class EvalCase:
    id: str
    category: str
    input: str
    expected_keywords: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    reference_sources: list[str] = field(default_factory=list)


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
                    expected_keywords=list(data.get("expected_keywords", [])),
                    required_tools=list(data.get("required_tools", [])),
                    reference_sources=list(data.get("reference_sources", [])),
                )
            )

    return cases
