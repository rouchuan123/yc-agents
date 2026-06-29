import sys

from yc_agents.analytics.config import AnalyticsConfig
from yc_agents.analytics.recorder import AnalyticsRecorder
from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.harness.permissions import HumanApprovalGate
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.harness.tool_schema import ToolField, ToolSchema
from yc_agents.intent.llm_classifier import LLMIntentClassifier
from yc_agents.intent.router import IntentRouter
from yc_agents.intent.rule_matcher import RuleIntentMatcher
from yc_agents.intent.semantic_matcher import SemanticIntentMatcher
from yc_agents.mcp.stdio_client import StdioMCPClient
from yc_agents.memory.compressor import MemoryCompressor
from yc_agents.memory.profile import CodeAgentProfileMemory
from yc_agents.memory.session import SessionMemory
from yc_agents.memory.summary import SummaryMemory
from yc_agents.prompts.builder import PromptBuilder
from yc_agents.prompts.project_instructions import ProjectInstructionLoader
from yc_agents.rag.embeddings import DeterministicEmbeddingProvider
from yc_agents.rag.hybrid_retriever import HybridRetriever
from yc_agents.rag.keyword_index import KeywordIndex
from yc_agents.rag.vector_store import VectorStore
from yc_agents.tools.file_reader import FileReaderTool
from yc_agents.tools.code_search import CodeSearchTool
from yc_agents.tools.command_reader import CommandReaderTool
from yc_agents.tools.git_inspector import GitInspectorTool
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.mcp_adapter import MCPToolAdapter
from yc_agents.tools.rag_search import RAGSearchTool
from yc_agents.tools.registry import ToolRegistry
from yc_agents.tools.verification_runner import VerificationRunnerTool
from yc_agents.tools.web_search import WebSearchTool
from yc_agents.tools.workspace_files import WorkspaceFilesTool


def build_cli_runtime(session, llm=None, skills_dir="skills"):
    llm = llm or YCAgentsLLM()
    analytics_config = AnalyticsConfig.from_env(session.workspace.path)
    analytics_recorder = (
        AnalyticsRecorder(analytics_config, session_id=session.id)
        if analytics_config.analytics_enabled
        else None
    )
    managed_resources = []
    session_memory = SessionMemory(file_path=session.messages_path)
    summary_memory = SummaryMemory(file_path=session.summary_path)
    profile_memory = CodeAgentProfileMemory(file_path=session.profile_path)
    memory_compressor = MemoryCompressor(summary_memory=summary_memory)
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
    available_tools = [
        "workspace_files",
        "file_reader",
        "markdown_writer",
        "rag_search",
        "web_search",
        "git_inspector",
        "code_search",
        "verification_runner",
        "command_reader",
    ]
    if analytics_config.sqlite_mcp_enabled:
        available_tools.extend(
            [
                "mcp_sqlite_list_tables",
                "mcp_sqlite_describe_table",
                "mcp_sqlite_query_readonly",
            ]
        )
    agent = SkillRuntimeAgent(
        llm,
        skills_dir=skills_dir,
        session_memory=session_memory,
        summary_memory=summary_memory,
        profile_memory=profile_memory,
        memory_compressor=memory_compressor,
        compression_threshold=12,
        rag_search_tool=rag_search_tool,
        prompt_builder=prompt_builder,
        intent_router=intent_router,
        workspace_context={
            "name": session.workspace.name,
            "path": str(session.workspace.path),
            "ycore_dir": str(session.workspace.ycore_dir),
            "available_tools": available_tools,
        },
    )
    tool_registry = ToolRegistry()
    tool_registry.register(MarkdownWriterTool())
    tool_registry.register(WorkspaceFilesTool(session.workspace.path))
    tool_registry.register(FileReaderTool(session.workspace.path))
    tool_registry.register(GitInspectorTool(session.workspace.path))
    tool_registry.register(CodeSearchTool(session.workspace.path))
    tool_registry.register(CommandReaderTool(session.workspace.path))
    tool_registry.register(VerificationRunnerTool(session.workspace.path))
    tool_registry.register(WebSearchTool())
    tool_registry.register(rag_search_tool)
    if analytics_config.sqlite_mcp_enabled:
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
        tool_registry.register(
            MCPToolAdapter(
                name="mcp_sqlite_list_tables",
                description="List YCore analytics SQLite tables.",
                server_name="sqlite",
                tool_name="sqlite.list_tables",
                client=sqlite_client,
            )
        )
        tool_registry.register(
            MCPToolAdapter(
                name="mcp_sqlite_describe_table",
                description="Describe one YCore analytics SQLite table.",
                server_name="sqlite",
                tool_name="sqlite.describe_table",
                client=sqlite_client,
                schema=ToolSchema(
                    fields=[ToolField(name="table", type="str", required=True)]
                ),
            )
        )
        tool_registry.register(
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
            )
        )

    return YCAgentRuntime(
        agent,
        expects_json=True,
        tool_registry=tool_registry,
        allowed_tools=available_tools,
        approval_gate=HumanApprovalGate(),
        output_root=session.runs_path,
        analytics_recorder=analytics_recorder,
        managed_resources=managed_resources,
    )
