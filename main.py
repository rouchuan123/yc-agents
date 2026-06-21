from dotenv import load_dotenv

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.harness.permissions import HumanApprovalGate
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.compressor import MemoryCompressor
from yc_agents.memory.profile import ResearchProfileMemory
from yc_agents.memory.session import SessionMemory
from yc_agents.memory.summary import SummaryMemory
from yc_agents.rag.keyword_index import KeywordIndex
from yc_agents.tools.docx_reader import DocxReaderTool
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.rag_search import RAGSearchTool
from yc_agents.tools.registry import ToolRegistry


def build_runtime():
    llm = YCAgentsLLM()
    session_memory = SessionMemory()
    summary_memory = SummaryMemory()
    profile_memory = ResearchProfileMemory()
    memory_compressor = MemoryCompressor(summary_memory=summary_memory)
    rag_search_tool = RAGSearchTool(KeywordIndex())
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

    while True:
        user_input = input("你：")

        if user_input in ["退出", "exit", "quit"]:
            break

        response = runtime.run(user_input)

        print("YC Agent：", response)


if __name__ == "__main__":
    main()
