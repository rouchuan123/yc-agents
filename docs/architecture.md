# YCore Architecture

## Runtime Boundary

`YCAgentRuntime` owns run orchestration. It accepts user input, calls the Agent, handles the JSON protocol, dispatches tool calls through `ToolGateway`, writes run outputs, records trace events, and persists state checkpoints.

## Agent Boundary

`SkillRuntimeAgent` decides how user input maps to a skill and prepares the prompt context used for execution. It injects memory, summary context, profile context, and RAG snippets before asking the LLM for a final response or a tool call.

## Skill System

`SkillLoader` reads `SKILL.md`, expanded front matter, references, scripts, and assets from the `skills` directory. `SkillRegistry` stores the loaded `SkillDefinition` objects and supports top-k discovery through `SkillDiscoveryIndex`.

The selection step uses skill summaries: name, description, triggers, inputs, outputs, and allowed tools. Full skill body content is used after a skill is selected.

## Tool System

`ToolGateway` is the harness boundary for tool execution. It checks whether a tool is allowed, validates schema-backed arguments, applies max-call and repeated-call policy, asks `HumanApprovalGate` whether approval is needed, executes the tool with timeout/retry policy, returns structured failures, and records trace events. Existing tools include Markdown writing, DOCX reading, and RAG search.

## RAG System

Current RAG components include `DocumentChunker`, `DocumentChunk`, document loaders, `KeywordIndex`, `VectorStore`, `HybridRetriever`, `QueryTermReranker`, embedding provider interfaces, and `RAGCitationFormatter`.

RAG pipeline: document loader -> metadata chunker -> keyword index -> embedding provider -> vector store -> hybrid retrieval -> rerank -> citation formatter -> Agent context.

The default local test path uses deterministic embeddings so unit tests do not require network access. API and local HTTP embedding providers are dependency-injected boundaries for OpenAI-compatible APIs or future local embedding services.

## Memory System

The Agent can use session memory, summary memory, profile memory, and `MemoryCompressor`. This separates short-term conversation context from compressed summaries and durable user/research profile notes.

## Trace And State

`TraceRecorder` records structured events for runtime behavior. `StateStore` persists checkpoint state so each run has inspectable artifacts under `outputs/runs/<run_id>`. Runtime checkpoints store user input, and `YCAgentRuntime.resume_from_state` provides conservative replay from saved input plus an optional redirect instruction.

## Desktop Boundary

The desktop backend in `yc_agents/desktop` exposes runtime operations through FastAPI. The `desktop` app is an Electron and React shell for starting runs and viewing run artifacts. The desktop UI is an observability surface for status, trace, tool calls, and approvals, not the core Agent intelligence.

## MCP Boundary

MCP is treated as the protocol boundary for external tools/resources. Function Calling is how the model asks to call a tool; `ToolGateway` is the harness layer that validates and controls that call; MCP is one possible source of tools behind the gateway.

The repository includes `mcp_servers.json` for a filesystem MCP server demo and a testable `MCPClientConfig`/`StaticMCPClient` boundary. Unit tests do not start `npx` or external MCP subprocesses.

## Failure Handling Model

Current failure handling includes JSON-protocol fallback events, allowed-tool checks, schema validation, approval-state tracing, timeout, retry, repeated-call detection, max-call control, structured tool failures, and output persistence. Tool failures are returned to the Agent as observations so the model can explain or revise strategy.

## Current Limitations

- The default runtime has an empty in-memory RAG index until documents are loaded.
- RAG evaluation cases exist, but aggregate retrieval metrics require running the evaluation harness against a populated corpus.
- ToolGateway policy is in-memory per runtime gateway instance; distributed or persistent tool budgets are not implemented.
- Resume is conservative user-input replay, not a full VM-style continuation of every intermediate frame.
- MCP configuration and adapter boundaries exist; production subprocess lifecycle management is intentionally outside this prototype.

## Interview Mapping

- Runtime boundary: `YCAgentRuntime`.
- Agent boundary: `SkillRuntimeAgent`.
- Skill loading: `SkillLoader` and `SkillRegistry`.
- Tool safety boundary: `ToolGateway` and `HumanApprovalGate`.
- Observability: `TraceRecorder`, `StateStore`, and desktop run views.
- RAG boundary: chunker, index/store, search tool, and citation formatter.
