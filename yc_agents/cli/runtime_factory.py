import sys

from yc_agents.analytics.config import AnalyticsConfig
from yc_agents.analytics.recorder import AnalyticsRecorder
from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.config.ycore import YCoreConfig
from yc_agents.core.config import ProviderConfig
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.harness.permissions import HumanApprovalGate
from yc_agents.harness.recovery import RecoveryPolicy
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.harness.tool_policy import ToolExecutionPolicy
from yc_agents.intent.llm_classifier import LLMIntentClassifier
from yc_agents.intent.router import IntentRouter
from yc_agents.intent.rule_matcher import RuleIntentMatcher
from yc_agents.intent.semantic_matcher import SemanticIntentMatcher
from yc_agents.mcp.stdio_client import StdioMCPClient
from yc_agents.memory.compressor import MemoryCompressor
from yc_agents.memory.long_term import LongTermMemory
from yc_agents.memory.profile import CodeAgentProfileMemory
from yc_agents.memory.session import SessionMemory
from yc_agents.memory.summary import SummaryMemory
from yc_agents.prompts.builder import PromptBuilder
from yc_agents.prompts.project_instructions import ProjectInstructionLoader
from yc_agents.rag.embeddings import APIEmbeddingProvider, DeterministicEmbeddingProvider
from yc_agents.rag.hybrid_retriever import HybridRetriever
from yc_agents.rag.keyword_index import KeywordIndex
from yc_agents.rag.vector_store import VectorStore
from yc_agents.tools.file_reader import FileReaderTool
from yc_agents.tools.code_search import CodeSearchTool
from yc_agents.tools.command_reader import CommandReaderTool
from yc_agents.tools.git_inspector import GitInspectorTool
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.memory_search import MemorySearchTool
from yc_agents.tools.mcp_adapter import MCPToolAdapter
from yc_agents.tools.rag_search import RAGSearchTool
from yc_agents.tools.registry import ToolRegistry
from yc_agents.tools.verification_runner import VerificationRunnerTool
from yc_agents.tools.web_search import TavilyWebSearchProvider, WebSearchTool
from yc_agents.tools.workspace_files import WorkspaceFilesTool
from yc_agents.tools.workspace_write import WorkspaceWriteTool


def build_cli_runtime(session, llm=None, skills_dir=None):
    ycore_config = YCoreConfig.load(session.workspace.path)
    provider_settings = ycore_config.resolve_model_provider()
    provider_config = ProviderConfig.from_ycore(provider_settings)
    if llm is None:
        llm = YCAgentsLLM(config=provider_config)
    set_usage_path = getattr(llm, "set_usage_path", None)
    if callable(set_usage_path):
        set_usage_path(session.usage_path)

    analytics_config = AnalyticsConfig.from_ycore(
        session.workspace.path,
        ycore_config.analytics_data(),
    )
    runtime_config = ycore_config.runtime_data()
    memory_config = ycore_config.memory_data()
    configured_enabled_tools = ycore_config.enabled_tools()
    enabled_tool_names = set(configured_enabled_tools)
    compression_threshold = int(memory_config.get("compressionThreshold", 12))
    resolved_skills_dir = skills_dir or ycore_config.skills_dirs()[0]
    analytics_recorder = (
        AnalyticsRecorder(analytics_config, session_id=session.id)
        if analytics_config.analytics_enabled
        else None
    )
    managed_resources = []
    session_memory = SessionMemory(file_path=session.messages_path)
    summary_memory = SummaryMemory(file_path=session.summary_path)
    profile_memory = CodeAgentProfileMemory(file_path=session.profile_path)
    memory_compressor = MemoryCompressor(summary_memory=summary_memory, llm=llm)
    memory_embedding = None
    embedding_config = dict(memory_config.get("embedding") or {})
    if embedding_config.get("enabled") and getattr(llm, "client", None) is not None:
        memory_embedding = APIEmbeddingProvider(
            llm.client,
            model=embedding_config.get("model", "text-embedding-3-small"),
        )
    long_term_memory = None
    if memory_config.get("enabled", True):
        long_term_memory = LongTermMemory(
            session.workspace.path,
            global_dir=memory_config.get("globalDir"),
            embedding_provider=memory_embedding,
            min_score=float(memory_config.get("minScore", 0.2)),
            session_half_life_days=float(memory_config.get("sessionHalfLifeDays", 30)),
            dream_config=memory_config.get("dream") or {},
            llm=llm,
        )
    keyword_index = KeywordIndex()
    vector_store = VectorStore(
        embedding_provider=DeterministicEmbeddingProvider(),
    )
    rag_retriever = HybridRetriever(
        keyword_index=keyword_index,
        vector_store=vector_store,
    )
    rag_search_tool = RAGSearchTool(rag_retriever)
    project_instructions = ProjectInstructionLoader(session.workspace.path).load()
    prompt_builder = PromptBuilder(project_instructions=project_instructions)
    intent_router = IntentRouter(
        rule_matcher=RuleIntentMatcher(),
        semantic_matcher=SemanticIntentMatcher(),
        llm_classifier=LLMIntentClassifier(llm),
    )
    tool_policy = ToolExecutionPolicy(
        max_calls=int(runtime_config.get("maxToolCalls", 12)),
        timeout_seconds=int(runtime_config.get("toolTimeoutSeconds", 30)),
        max_retries=int(runtime_config.get("toolExecutionRetryCount", 1)),
    )
    recovery_policy = RecoveryPolicy(
        protocol_retries=int(runtime_config.get("invalidJsonRetryCount", 2)),
        provider_retries=int(runtime_config.get("providerRetryCount", 1)),
        verification_retries=int(runtime_config.get("verificationRetryCount", 1)),
        max_attempts=int(runtime_config.get("maxRecoveryAttempts", 4)),
        provider_backoff_seconds=float(
            runtime_config.get("providerRetryBackoffSeconds", 1)
        ),
    )
    tool_registry = ToolRegistry()
    def register_enabled(tool):
        if tool.name in enabled_tool_names:
            tool_registry.register(tool)

    register_enabled(MarkdownWriterTool(output_dir=session.workspace.path))
    register_enabled(WorkspaceFilesTool(session.workspace.path))
    register_enabled(FileReaderTool(session.workspace.path))
    register_enabled(WorkspaceWriteTool(session.workspace.path))
    register_enabled(GitInspectorTool(session.workspace.path))
    register_enabled(CodeSearchTool(session.workspace.path))
    register_enabled(CommandReaderTool(session.workspace.path))
    register_enabled(VerificationRunnerTool(session.workspace.path))
    register_enabled(
        WebSearchTool(
            provider=TavilyWebSearchProvider(
                api_key=ycore_config.resolve_web_search_api_key()
            )
        )
    )
    register_enabled(rag_search_tool)
    if long_term_memory is not None and "memory_search" in enabled_tool_names:
        memory_search_tool = MemorySearchTool(
            long_term_memory,
            session_id=session.id,
            token_budget=int(memory_config.get("retrievalTokenBudget", 4_000)),
        )
        tool_registry.register(memory_search_tool)
    sqlite_tool_names = {
        "mcp_sqlite_list_tables",
        "mcp_sqlite_describe_table",
        "mcp_sqlite_query_readonly",
    }
    enabled_sqlite_tools = enabled_tool_names & sqlite_tool_names
    if analytics_config.sqlite_mcp_enabled and enabled_sqlite_tools:
        sqlite_client = StdioMCPClient(
            command=[
                sys.executable,
                "-m",
                "yc_agents.mcp.sqlite_server",
                "--db",
                str(analytics_config.db_path),
                "--workspace",
                str(session.workspace.path),
                "--max-rows",
                str(analytics_config.max_rows),
            ],
            server_name="sqlite",
            timeout_seconds=10,
        )
        try:
            sqlite_client.start()
        except Exception:
            pass
        managed_resources.append(sqlite_client)
        sqlite_tools = [
            MCPToolAdapter(
                name="mcp_sqlite_list_tables",
                description="List YCore analytics SQLite tables.",
                server_name="sqlite",
                tool_name="sqlite.list_tables",
                client=sqlite_client,
            ),
            MCPToolAdapter(
                name="mcp_sqlite_describe_table",
                description="Describe one YCore analytics SQLite table.",
                server_name="sqlite",
                tool_name="sqlite.describe_table",
                client=sqlite_client,
                schema=ToolSchema(
                    fields=[ToolField(name="table", type="str", required=True)]
                ),
            ),
            MCPToolAdapter(
                name="mcp_sqlite_query_readonly",
                description=(
                    "Run one read-only SELECT query against YCore analytics SQLite."
                ),
                server_name="sqlite",
                tool_name="sqlite.query_readonly",
                client=sqlite_client,
                schema=ToolSchema(
                    fields=[ToolField(name="sql", type="str", required=True)]
                ),
            ),
        ]
        for sqlite_tool in sqlite_tools:
            register_enabled(sqlite_tool)

    registered_names = set(tool_registry.tools)
    available_tools = [
        name for name in configured_enabled_tools if name in registered_names
    ]
    agent = SkillRuntimeAgent(
        llm,
        skills_dir=resolved_skills_dir,
        session_memory=session_memory,
        summary_memory=summary_memory,
        profile_memory=profile_memory,
        memory_compressor=memory_compressor,
        compression_threshold=compression_threshold,
        memory_config=memory_config,
        context_limit=provider_config.context_window or 8000,
        max_output_tokens=provider_config.max_output_tokens or 0,
        long_term_memory=long_term_memory,
        session_id=session.id,
        rag_search_tool=rag_search_tool,
        prompt_builder=prompt_builder,
        intent_router=intent_router,
        workspace_context={
            "name": session.workspace.name,
            "path": str(session.workspace.path),
            "ycore_dir": str(session.workspace.ycore_dir),
            "available_tools": available_tools,
            "tool_catalog": tool_registry.list_tools(),
        },
    )

    return YCAgentRuntime(
        agent,
        expects_json=True,
        tool_registry=tool_registry,
        allowed_tools=available_tools,
        approval_gate=HumanApprovalGate(project_root=session.workspace.path),
        output_root=session.runs_path,
        tool_policy=tool_policy,
        recovery_policy=recovery_policy,
        invalid_json_retry_count=int(runtime_config.get("invalidJsonRetryCount", 0)),
        fail_on_invalid_json=bool(runtime_config.get("failOnInvalidJson", False)),
        analytics_recorder=analytics_recorder,
        managed_resources=managed_resources,
        context_limit=provider_config.context_window or 8000,
    )
