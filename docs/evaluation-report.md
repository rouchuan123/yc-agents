# YCore Evaluation Report

## Purpose

This report tracks whether the Agent succeeds on research workflow tasks, not only whether unit tests pass.

## Case Set

- Total cases: 30
- Categories: literature review, opening report, system design, RAG QA, tool use
- Additional RAG-specific cases: 10 in `eval/cases/rag_cases.jsonl`

## Metrics

- Task success rate: keyword-based baseline before human grading
- Tool success rate: planned after ToolGateway trace metrics are expanded
- Retrieval hit rate: planned after RAG metadata and citation metrics are expanded
- Citation precision: planned after citation-aware RAG output is implemented
- Average latency: measured by the eval runner

RAG-specific metrics can use `retrieval_hit` and `citation_precision` once a populated corpus and citation extraction layer are wired into the runner output.

## Current Baseline

Run:

```powershell
python -m yc_agents.eval.runner --cases eval/cases/research_agent_cases.jsonl --output outputs/eval/baseline.json
```

The first baseline should be generated with valid model credentials or a deterministic runtime adapter for local verification. Do not report aggregate success numbers until the baseline output has been reviewed.
