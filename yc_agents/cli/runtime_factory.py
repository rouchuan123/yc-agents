from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.harness.permissions import HumanApprovalGate
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.compressor import MemoryCompressor
from yc_agents.memory.profile import ResearchProfileMemory
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
from yc_agents.tools.git_inspector import GitInspectorTool
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.rag_search import RAGSearchTool
from yc_agents.tools.registry import ToolRegistry
from yc_agents.tools.verification_runner import VerificationRunnerTool
from yc_agents.tools.web_search import WebSearchTool
from yc_agents.tools.workspace_files import WorkspaceFilesTool


def build_cli_runtime(session, llm=None, skills_dir="skills"):
    llm = llm or YCAgentsLLM()
    session_memory = SessionMemory(file_path=session.messages_path)
    summary_memory = SummaryMemory(file_path=session.summary_path)
    profile_memory = ResearchProfileMemory(file_path=session.profile_path)
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
        workspace_context={
            "name": session.workspace.name,
            "path": str(session.workspace.path),
            "ycore_dir": str(session.workspace.ycore_dir),
            "available_tools": [
                "workspace_files",
                "file_reader",
                "markdown_writer",
                "rag_search",
                "web_search",
                "git_inspector",
                "code_search",
                "verification_runner",
            ],
        },
    )
    tool_registry = ToolRegistry()
    tool_registry.register(MarkdownWriterTool())
    tool_registry.register(WorkspaceFilesTool(session.workspace.path))
    tool_registry.register(FileReaderTool(session.workspace.path))
    tool_registry.register(GitInspectorTool(session.workspace.path))
    tool_registry.register(CodeSearchTool(session.workspace.path))
    tool_registry.register(VerificationRunnerTool(session.workspace.path))
    tool_registry.register(WebSearchTool())
    tool_registry.register(rag_search_tool)

    return YCAgentRuntime(
        agent,
        expects_json=True,
        tool_registry=tool_registry,
        allowed_tools=[
            "markdown_writer",
            "file_reader",
            "workspace_files",
            "rag_search",
            "web_search",
            "git_inspector",
            "code_search",
            "verification_runner",
        ],
        approval_gate=HumanApprovalGate(),
        output_root=session.runs_path,
    )
