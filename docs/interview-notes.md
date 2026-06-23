# YCore Interview Notes

## 60-Second Project Introduction

`YCore` is a Skill-driven Research Agent for graduate research workflows such as opening reports, literature review, and system design. I built it around explicit Agent runtime boundaries: skill selection, RAG context, tool execution, memory, trace, approval, and state persistence.

## Why This Is Not A Chatbot

A chatbot mainly maps one user message to one model response. This project routes the request through a runtime harness. The harness can select a skill, add memory and retrieval context, call tools through a gateway, ask for approval, record trace events, persist state, and write inspectable outputs.

## Hardest Technical Point

The hardest point is keeping model freedom inside engineering boundaries. The LLM can propose actions, but the runtime decides which tools are allowed, whether approval is needed, how outputs are recorded, and how failures become observable.

## Tool Calling Failure Handling

Tool failure is handled at the harness layer rather than hidden inside prompts. The ToolGateway validates arguments, checks permissions and approvals, applies timeout/retry policy, blocks repeated calls, records trace events, and returns structured errors so the model can correct parameters or switch strategy.

## RAG Explanation

Currently supports chunking, keyword search, and citation formatting boundaries. Planned next: metadata chunks, document loaders, API-first embeddings, local-provider compatibility, hybrid retrieval, reranking, citation-aware output, and RAG evaluation cases.

## Skill Discovery Explanation

Currently supports loading skills from `SKILL.md`, expanded metadata, top-k discovery, summary-first skill selection, and full skill loading after selection. Token budget estimation gives a simple pressure signal for future context trimming.

## Memory And State Explanation

Currently supports session, summary, profile memory, trace recording, explicit statuses, state checkpoint files, and conservative resume from saved user input plus optional redirect instruction. It is not a full VM-style continuation; it is a practical Agent task recovery path for failed or interrupted runs.

## Evaluation Explanation

Current verification is unit-test based. Planned next: a 30-case evaluation set with keyword-based task success, latency, and later tool/retrieval/citation metrics.

## MCP Explanation

MCP is treated as the protocol boundary for external tools/resources. Function Calling is how the model asks to call a tool; ToolGateway is the harness layer that validates and controls that call; MCP is one possible source of tools behind the gateway.

## Desktop Explanation

The desktop app is not the core Agent intelligence. It is the observability surface for status, trace, tool calls, and approvals.

## Engineering Credibility

The project declares Python metadata in `pyproject.toml`, keeps dependency commands in README, and provides `scripts/test.ps1` for Python tests, desktop tests, and desktop build. It is positioned as an interview-ready engineering prototype, not a fake production platform.
