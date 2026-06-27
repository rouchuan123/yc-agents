from dotenv import load_dotenv

from yc_agents.cli.app import run_tui
from yc_agents.cli.runtime_factory import build_cli_runtime
from yc_agents.cli.sessions import CLISessionStore
from yc_agents.cli.workspaces import WorkspaceStore
from yc_agents.core.llm import YCAgentsLLM
from yc_agents.tools.mcp_adapter import MCPToolAdapter
from yc_agents.tools.mcp_client import MCPClientConfig


def build_mcp_tools(config_path="mcp_servers.json", client=None):
    if client is None:
        return []

    config = MCPClientConfig.from_file(config_path)
    tools = []

    for server_name, server in config.servers.items():
        declared_tools = server.get("tools") or [
            {
                "name": "call",
                "description": server.get("description", f"MCP server: {server_name}"),
            }
        ]

        for declared_tool in declared_tools:
            tool_name = declared_tool["name"]
            tools.append(
                MCPToolAdapter(
                    name=f"mcp_{server_name}_{tool_name}",
                    description=declared_tool.get(
                        "description",
                        f"MCP tool {server_name}.{tool_name}",
                    ),
                    server_name=server_name,
                    tool_name=tool_name,
                    client=client,
                )
            )

    return tools


def build_runtime():
    workspace = WorkspaceStore().ensure_active_workspace()
    session = CLISessionStore(workspace).ensure_current_session()
    return build_cli_runtime(session, llm=YCAgentsLLM())


def main():
    load_dotenv()
    workspace_store = WorkspaceStore()
    workspace = workspace_store.ensure_active_workspace()
    session_store = CLISessionStore(workspace)
    session = session_store.ensure_current_session()
    runtime = build_cli_runtime(session, llm=YCAgentsLLM())
    run_tui(
        runtime,
        workspace_store=workspace_store,
        workspace=workspace,
        session_store=session_store,
        session=session,
        runtime_builder=build_cli_runtime,
    )


if __name__ == "__main__":
    main()
