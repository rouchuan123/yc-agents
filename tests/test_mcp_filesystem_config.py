import json
from pathlib import Path

from yc_agents.tools.mcp_client import MCPClientConfig


def test_filesystem_mcp_server_config_exists():
    config = json.loads(Path("mcp_servers.json").read_text(encoding="utf-8"))

    assert "filesystem" in config["servers"]
    server = config["servers"]["filesystem"]
    assert server["type"] == "stdio"
    assert "command" in server
    assert isinstance(server["args"], list)


def test_mcp_client_config_parses_servers_and_tools(tmp_path):
    path = tmp_path / "mcp_servers.json"
    path.write_text(
        json.dumps(
            {
                "servers": {
                    "filesystem": {
                        "description": "Local filesystem MCP boundary",
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
                        "tools": [
                            {"name": "read_file", "description": "Read a file"}
                        ],
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = MCPClientConfig.from_file(path)

    server = config.servers["filesystem"]
    assert server["description"] == "Local filesystem MCP boundary"
    assert server["tools"][0]["name"] == "read_file"
