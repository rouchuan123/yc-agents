from dotenv import load_dotenv

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.memory.session import SessionMemory
from yc_agents.tools.markdown_writer import MarkdownWriterTool
from yc_agents.tools.registry import ToolRegistry


def build_runtime():
    llm = YCAgentsLLM()
    session_memory = SessionMemory()
    agent = SkillRuntimeAgent(llm, session_memory=session_memory)
    tool_registry = ToolRegistry()
    tool_registry.register(MarkdownWriterTool())

    return YCAgentRuntime(
        agent,
        expects_json=True,
        tool_registry=tool_registry,
        allowed_tools=["markdown_writer"],
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
