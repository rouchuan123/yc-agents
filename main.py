from dotenv import load_dotenv

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.cli.app import run_tui
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.harness.permissions import HumanApprovalGate
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.compressor import MemoryCompressor
from yc_agents.memory.profile import ResearchProfileMemory
from yc_agents.memory.session import SessionMemory
from yc_agents.memory.summary import SummaryMemory
from yc_agents.rag.embeddings import DeterministicEmbeddingProvider
from yc_agents.rag.hybrid_retriever import HybridRetriever
from yc_agents.rag.keyword_index import KeywordIndex
from yc_agents.rag.vector_store import VectorStore
from yc_agents.tools.docx_reader import DocxReaderTool
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.mcp_adapter import MCPToolAdapter
from yc_agents.tools.mcp_client import MCPClientConfig
from yc_agents.tools.rag_search import RAGSearchTool
from yc_agents.tools.registry import ToolRegistry


def build_mcp_tools(config_path="mcp_servers.json", client=None):
    if client is None:
        return []

    config = MCPClientConfig.from_file(config_path)
    tools = []

    for server_name, server in config.servers.items():
        tools.append(
            MCPToolAdapter(
                name=f"mcp_{server_name}",
                description=server.get("description", f"MCP server: {server_name}"),
                server_name=server_name,
                tool_name="call",
                client=client,
            )
        )

    return tools


def build_runtime():
    llm = YCAgentsLLM()
    session_memory = SessionMemory()
    summary_memory = SummaryMemory()
    profile_memory = ResearchProfileMemory()
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
    agent = SkillRuntimeAgent(
        llm,
        session_memory=session_memory,
        summary_memory=summary_memory,
        profile_memory=profile_memory,
        memory_compressor=memory_compressor,
        compression_threshold=12,
        rag_search_tool=rag_search_tool,
    )
    tool_registry = ToolRegistry()
    tool_registry.register(MarkdownWriterTool())
    tool_registry.register(DocxReaderTool())
    tool_registry.register(rag_search_tool)

    return YCAgentRuntime(
        agent,
        expects_json=True,
        tool_registry=tool_registry,
        allowed_tools=["markdown_writer", "docx_reader", "rag_search"],
        approval_gate=HumanApprovalGate(),
    )


def main():
    load_dotenv()
    runtime = build_runtime()
    run_tui(runtime)


if __name__ == "__main__":
    main()
