import sys
import threading
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from yc_agents.analytics.config import AnalyticsConfig
from yc_agents.analytics.recorder import AnalyticsRecorder
from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.config.ycore import YCoreConfig
from yc_agents.core.config import ProviderConfig
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.core.model_router import ModelRouter
from yc_agents.documents.analyzer import DocxTemplateAnalyzer
from yc_agents.documents.attachments import AttachmentManager
from yc_agents.documents.broker import ExecutionBroker
from yc_agents.documents.builder import DocxBuilder
from yc_agents.documents.content import DocumentContentStore
from yc_agents.documents.editor import DocxEditor
from yc_agents.documents.jobs import DocumentJobStore
from yc_agents.documents.sources import DocumentSourceService
from yc_agents.documents.verifier import DocxVerifier
from yc_agents.documents.vision import VisionQAService
from yc_agents.harness.permissions import HumanApprovalGate
from yc_agents.harness.recovery import RecoveryPolicy
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.harness.token_budget import TokenBudgetPolicy
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
from yc_agents.rag.embeddings import APIEmbeddingProvider
from yc_agents.rag.keyword_index import KeywordIndex
from yc_agents.rag.knowledge_index import RAGKnowledgeIndex
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
from yc_agents.tools.document_job import DocumentJobTool
from yc_agents.tools.docx_template import DocxTemplateAnalyzerTool, DocxTemplateQueryTool
from yc_agents.tools.document_source import DocumentSourceTool
from yc_agents.tools.document_content import DocumentContentTool
from yc_agents.tools.docx_generate import DocxGenerateTool
from yc_agents.tools.docx_edit import DocxEditTool
from yc_agents.tools.docx_verify import DocxVerifyTool


@dataclass
class WorkspaceServices:
    """workspace 级共享组件：配置解析、RAG 索引、workspace 工具与 MCP
    sqlite 子进程。同一 workspace 内切换 session 时按引用复用，避免每次
    重建 runtime 都重扫知识库、重启子进程。"""

    workspace_path: Path
    ycore_config: YCoreConfig
    analytics_config: AnalyticsConfig
    keyword_index: KeywordIndex
    rag_index_report: dict
    rag_search_tool: RAGSearchTool
    workspace_tools: list = field(default_factory=list)
    sqlite_client: object = None
    sqlite_tools: list = field(default_factory=list)

    @property
    def workspace_tools_by_name(self):
        return {tool.name: tool for tool in self.workspace_tools}

    def close(self):
        client = self.sqlite_client
        self.sqlite_client = None
        if client is not None:
            with suppress(Exception):
                client.close()


_workspace_services_cache = {}
_workspace_services_lock = threading.Lock()


def _workspace_cache_key(workspace_path):
    return str(Path(workspace_path).resolve())


def get_workspace_services(workspace_path):
    """按 workspace 路径缓存的 services 入口：首次访问构建并缓存，之后
    的 session 切换直接复用；workspace 切换时调用
    invalidate_workspace_services 失效。"""
    key = _workspace_cache_key(workspace_path)
    with _workspace_services_lock:
        cached = _workspace_services_cache.get(key)
    if cached is not None:
        return cached

    services = build_workspace_services(workspace_path)
    with _workspace_services_lock:
        existing = _workspace_services_cache.get(key)
        if existing is not None:
            # 并发构建竞态：保留先入缓存的实例，释放自己这份资源。
            services.close()
            return existing
        _workspace_services_cache[key] = services
    return services


def invalidate_workspace_services(workspace_path=None):
    """失效 workspace 级缓存并释放其持有的资源；不传路径时清空全部。"""
    with _workspace_services_lock:
        if workspace_path is None:
            stale = list(_workspace_services_cache.values())
            _workspace_services_cache.clear()
        else:
            services = _workspace_services_cache.pop(
                _workspace_cache_key(workspace_path), None
            )
            stale = [services] if services is not None else []
    for services in stale:
        services.close()


def build_workspace_services(workspace_path, ycore_config=None):
    """构建 workspace 级组件（配置解析、RAG 索引、workspace 工具、MCP
    sqlite client）。session 级组件见 build_cli_runtime。"""
    workspace_path = Path(workspace_path)
    if ycore_config is None:
        ycore_config = YCoreConfig.load(workspace_path)

    analytics_config = AnalyticsConfig.from_ycore(
        workspace_path,
        ycore_config.analytics_data(),
    )
    rag_config = ycore_config.rag_data()
    enabled_tool_names = set(ycore_config.enabled_tools())

    keyword_index = KeywordIndex()
    rag_enabled = bool(rag_config.get("enabled", True))
    rag_retrieval = str(rag_config.get("retrieval", "bm25")).lower()
    if rag_retrieval != "bm25":
        raise ValueError(
            f"Unsupported RAG retrieval mode: {rag_retrieval}. "
            "The minimal RAG pipeline currently supports only bm25."
        )
    rag_index_report = {
        "enabled": rag_enabled,
        "retrieval": rag_retrieval,
        "documents": 0,
        "chunks": 0,
        "scopes": [],
        "errors": [],
    }
    if rag_enabled and "rag_search" in enabled_tool_names:
        scope_configs = [
            (
                ycore_config.global_config_root(),
                rag_config.get("globalDir", "data/RAG_knowledge"),
                "global",
                False,
            ),
            (
                workspace_path,
                rag_config.get(
                    "workspaceDir",
                    ".ycore/memory/RAG_knowledge",
                ),
                "workspace",
                True,
            ),
        ]
        for root_dir, knowledge_dir, scope, create in scope_configs:
            scope_report = RAGKnowledgeIndex(
                root_dir,
                knowledge_dir,
                scope=scope,
                chunk_size=int(rag_config.get("chunkSize", 1200)),
                chunk_overlap=int(rag_config.get("chunkOverlap", 150)),
                keyword_index=keyword_index,
                create=create,
            ).build()
            rag_index_report["scopes"].append(scope_report)
            rag_index_report["documents"] += scope_report["documents"]
            rag_index_report["chunks"] += scope_report["chunks"]
            rag_index_report["errors"].extend(scope_report["errors"])
    rag_search_tool = RAGSearchTool(
        keyword_index,
        default_top_k=int(rag_config.get("topK", 4)),
    )

    workspace_tools = [
        MarkdownWriterTool(output_dir=workspace_path),
        WorkspaceFilesTool(workspace_path),
        FileReaderTool(workspace_path),
        WorkspaceWriteTool(workspace_path),
        GitInspectorTool(workspace_path),
        CodeSearchTool(workspace_path),
        CommandReaderTool(workspace_path),
        VerificationRunnerTool(workspace_path),
        WebSearchTool(
            provider=TavilyWebSearchProvider(
                api_key=ycore_config.resolve_web_search_api_key()
            )
        ),
    ]

    sqlite_client = None
    sqlite_tools = []
    sqlite_tool_names = {
        "mcp_sqlite_list_tables",
        "mcp_sqlite_describe_table",
        "mcp_sqlite_query_readonly",
    }
    if analytics_config.sqlite_mcp_enabled and (enabled_tool_names & sqlite_tool_names):
        sqlite_client = StdioMCPClient(
            command=[
                sys.executable,
                "-m",
                "yc_agents.mcp.sqlite_server",
                "--db",
                str(analytics_config.db_path),
                "--workspace",
                str(workspace_path),
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

    return WorkspaceServices(
        workspace_path=workspace_path,
        ycore_config=ycore_config,
        analytics_config=analytics_config,
        keyword_index=keyword_index,
        rag_index_report=rag_index_report,
        rag_search_tool=rag_search_tool,
        workspace_tools=workspace_tools,
        sqlite_client=sqlite_client,
        sqlite_tools=sqlite_tools,
    )


def _build_primary_llm(ycore_config, provider_config, runtime_config):
    """构造主模型 LLM；配置了有效 fallbacks 时用 ModelRouter 包装成
    容灾链（vision LLM 不走这里，保持单模型）。"""
    llm = YCAgentsLLM(config=provider_config)
    fallback_refs = ycore_config.fallback_model_refs()
    if not fallback_refs:
        return llm
    chain = [llm]
    for ref in fallback_refs:
        try:
            settings = ycore_config.resolve_model_provider(ref)
            fallback_config = ProviderConfig.from_ycore(settings)
        except (ValueError, RuntimeError):
            # fallback 是容灾配置：某个 ref 配错（provider 缺失、缺 API
            # key）不应拖垮主模型启动，跳过该 ref 即可；主模型自身的
            # 配置错误仍会在上层正常抛出。
            continue
        chain.append(
            YCAgentsLLM(config=fallback_config, usage_ledger=llm.usage_ledger)
        )
    if len(chain) == 1:
        return llm
    return ModelRouter(
        chain,
        retries_per_model=int(runtime_config.get("providerRetryCount", 1)),
        backoff_seconds=float(runtime_config.get("providerRetryBackoffSeconds", 1)),
    )


def build_cli_runtime(session, llm=None, skills_dir=None, workspace_services=None):
    # workspace 层：外部传入（TUI 缓存复用）或内部自建（保持旧行为，
    # 自建时 runtime 接管 MCP 子进程等资源的生命周期）。
    runtime_owns_workspace_resources = workspace_services is None
    services = workspace_services or build_workspace_services(session.workspace.path)
    ycore_config = services.ycore_config
    provider_settings = ycore_config.resolve_model_provider()
    provider_config = ProviderConfig.from_ycore(provider_settings)
    runtime_config = ycore_config.runtime_data()
    if llm is None:
        llm = _build_primary_llm(ycore_config, provider_config, runtime_config)
    set_usage_path = getattr(llm, "set_usage_path", None)
    if callable(set_usage_path):
        set_usage_path(session.usage_path)

    analytics_config = services.analytics_config
    memory_config = ycore_config.memory_data()
    rag_config = ycore_config.rag_data()
    documents_config = ycore_config.documents_data()
    configured_enabled_tools = ycore_config.enabled_tools()
    enabled_tool_names = set(configured_enabled_tools)
    skill_entries = ycore_config.skill_entries()
    enabled_skill_names = (
        set(ycore_config.enabled_skills()) if skill_entries else None
    )
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
    rag_enabled = bool(rag_config.get("enabled", True))
    rag_index_report = services.rag_index_report
    rag_search_tool = services.rag_search_tool
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
    recovery_policy = RecoveryPolicy.from_runtime_config(runtime_config)
    token_budget_policy = TokenBudgetPolicy.from_runtime_config(runtime_config)
    # 原生 function calling 需要两个条件同时满足：runtime.toolCalling 配置
    # 为 'native'，且 model entry 声明了 toolCalling 能力；否则一律走
    # json-protocol 文本协议（MiMo 等未标记的模型自动保持旧链路）。
    tool_calling_mode = str(
        runtime_config.get("toolCalling", "json-protocol") or "json-protocol"
    ).strip().lower()
    native_tool_calling = (
        tool_calling_mode == "native"
        and bool(getattr(provider_settings, "tool_calling", False))
    )
    tool_calling = "native" if native_tool_calling else "json-protocol"
    tool_registry = ToolRegistry()
    def register_enabled(tool):
        if tool.name in enabled_tool_names:
            tool_registry.register(tool)

    for workspace_tool in services.workspace_tools:
        register_enabled(workspace_tool)
    if rag_enabled:
        register_enabled(rag_search_tool)

    if bool(documents_config.get("enabled", True)):
        attachment_manager = AttachmentManager(session.path)
        document_job_store = DocumentJobStore(session.workspace.path, session.id)
        document_content_store = DocumentContentStore(document_job_store)
        document_analyzer = DocxTemplateAnalyzer(document_job_store)
        document_source_service = DocumentSourceService(
            session.workspace.path,
            document_job_store,
            chunk_size=int(rag_config.get("chunkSize", 1200)),
            chunk_overlap=int(rag_config.get("chunkOverlap", 150)),
        )
        document_builder = DocxBuilder(
            session.workspace.path,
            document_job_store,
            document_content_store,
        )
        document_editor = DocxEditor(session.workspace.path, document_job_store)
        document_jobs_root = session.workspace.path / ".ycore" / "document-jobs"
        document_outputs_root = session.workspace.path / "outputs"
        execution_broker = ExecutionBroker(
            read_roots=[document_jobs_root],
            write_roots=[document_jobs_root, document_outputs_root],
            timeout_seconds=int(documents_config.get("renderTimeoutSeconds", 300)),
        )
        vision_service = VisionQAService()
        visual_qa = dict(documents_config.get("visualQa") or {})
        if visual_qa.get("enabled", True):
            try:
                vision_settings = ycore_config.resolve_vision_model_provider()
                if vision_settings is not None:
                    vision_config = ProviderConfig.from_ycore(vision_settings)
                    vision_config.timeout = max(
                        1,
                        int(visual_qa.get("timeoutSeconds", 180)),
                    )
                    vision_llm = YCAgentsLLM(
                        config=vision_config,
                        usage_ledger=getattr(llm, "usage_ledger", None),
                    )
                    vision_service = VisionQAService(
                        vision_llm,
                        max_workers=int(visual_qa.get("maxWorkers", 1)),
                        retry_count=int(visual_qa.get("retryCount", 2)),
                        retry_backoff_seconds=float(
                            visual_qa.get("retryBackoffSeconds", 2)
                        ),
                    )
            except (ValueError, RuntimeError):
                vision_service = VisionQAService()
        document_verifier = DocxVerifier(
            document_job_store,
            broker=execution_broker,
            vision_service=vision_service,
        )
        document_tools = [
            DocumentJobTool(document_job_store, attachment_manager),
            DocxTemplateAnalyzerTool(document_analyzer),
            DocxTemplateQueryTool(document_analyzer),
            DocumentSourceTool(document_source_service),
            DocumentContentTool(document_content_store),
            DocxGenerateTool(document_builder),
            DocxEditTool(document_editor),
            DocxVerifyTool(document_verifier),
        ]
        for document_tool in document_tools:
            register_enabled(document_tool)
    if long_term_memory is not None and "memory_search" in enabled_tool_names:
        memory_search_tool = MemorySearchTool(
            long_term_memory,
            session_id=session.id,
            token_budget=int(memory_config.get("retrievalTokenBudget", 4_000)),
        )
        tool_registry.register(memory_search_tool)
    if services.sqlite_client is not None:
        if runtime_owns_workspace_resources:
            # 自建 services：MCP 子进程随 runtime.close() 一起关闭，
            # 维持旧行为；注入的缓存 services 则由 workspace 层持有。
            managed_resources.append(services.sqlite_client)
        for sqlite_tool in services.sqlite_tools:
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
            "rag": rag_index_report,
        },
        enabled_skills=enabled_skill_names,
        tool_calling=tool_calling,
        native_tools=(
            tool_registry.to_openai_schema() if native_tool_calling else None
        ),
    )

    return YCAgentRuntime(
        agent,
        expects_json=True,
        tool_registry=tool_registry,
        allowed_tools=available_tools,
        approval_gate=HumanApprovalGate(
            project_root=session.workspace.path,
            mode=ycore_config.approval_mode(),
        ),
        output_root=session.runs_path,
        tool_policy=tool_policy,
        recovery_policy=recovery_policy,
        token_budget_policy=token_budget_policy,
        invalid_json_retry_count=int(runtime_config.get("invalidJsonRetryCount", 0)),
        fail_on_invalid_json=bool(runtime_config.get("failOnInvalidJson", False)),
        analytics_recorder=analytics_recorder,
        managed_resources=managed_resources,
        context_limit=provider_config.context_window or 8000,
        tool_calling=tool_calling,
    )
