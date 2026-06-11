from dotenv import load_dotenv
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.agents.simple_agent import SimpleAgent
from yc_agents.harness.runtime import ResearchAgentHarness

load_dotenv()

llm = YCAgentsLLM()

agent = SimpleAgent(
    name="YC助手",
    llm=llm,
    system_prompt="你是一个耐心的小白编程老师"
)

harness = ResearchAgentHarness(agent)

history_file = "data/memory/session.json"
agent.load_history(history_file)

while True:
    user_input = input("你：")

    if user_input in ["退出", "exit", "quit"]:
        break

    response = harness.run(user_input)
    print("YC助手：", response)

    agent.save_history(history_file)
    