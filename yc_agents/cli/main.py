import argparse
import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from dotenv import dotenv_values

from yc_agents.cli.app import run_tui
from yc_agents.cli.runtime_factory import build_cli_runtime
from yc_agents.cli.sessions import CLISessionStore
from yc_agents.cli.workspaces import WorkspaceStore
from yc_agents.config.paths import env_template_path, source_checkout_root, ycore_home
from yc_agents.tools.mcp_adapter import MCPToolAdapter
from yc_agents.tools.mcp_client import MCPClientConfig


def package_version():
    try:
        return version("ycore")
    except PackageNotFoundError:
        return "0.1.0"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ycore",
        description="YCore local skill-driven CLI agent runtime.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {package_version()}",
    )
    return parser


def initialize_user_environment():
    home = ycore_home()
    home.mkdir(parents=True, exist_ok=True)
    user_env = home / ".env"
    if not user_env.exists():
        template = env_template_path()
        content = template.read_text(encoding="utf-8") if template.is_file() else ""
        user_env.write_text(content, encoding="utf-8")

    original_environment = dict(os.environ)
    source_root = source_checkout_root()
    env_paths = []
    if source_root is not None:
        env_paths.append(source_root / ".env")
    env_paths.append(user_env)

    merged = {}
    for path in env_paths:
        if path.is_file():
            merged.update(
                {
                    key: value
                    for key, value in dotenv_values(path).items()
                    if value
                }
            )

    for key, value in merged.items():
        if key not in original_environment:
            os.environ[key] = value
    return home


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


def build_runtime(startup_dir=None):
    startup_dir = Path(startup_dir or Path.cwd()).resolve()
    workspace_store = WorkspaceStore(startup_dir=startup_dir)
    workspace = workspace_store.add_workspace(startup_dir)
    session = CLISessionStore(workspace).ensure_current_session()
    return build_cli_runtime(session)


def main(argv=None):
    build_parser().parse_args(argv)
    initialize_user_environment()

    startup_dir = Path.cwd()
    workspace_store = WorkspaceStore(startup_dir=startup_dir)
    workspace = workspace_store.add_workspace(startup_dir)
    session_store = CLISessionStore(workspace)
    session = session_store.ensure_current_session()
    runtime = build_cli_runtime(session)
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
