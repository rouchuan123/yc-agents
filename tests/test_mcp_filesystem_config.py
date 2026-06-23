import json
from pathlib import Path


def test_filesystem_mcp_server_config_exists():
    config = json.loads(Path("mcp_servers.json").read_text(encoding="utf-8"))

    assert "filesystem" in config["servers"]
    server = config["servers"]["filesystem"]
    assert server["type"] == "stdio"
    assert "command" in server
    assert isinstance(server["args"], list)
