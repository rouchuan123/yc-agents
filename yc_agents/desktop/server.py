import os
from pathlib import Path

from dotenv import load_dotenv
import uvicorn

from yc_agents.desktop.app import create_app


def load_desktop_environment(repo_root=None):
    root = Path(repo_root or os.getcwd())
    load_dotenv(root / ".env")


def main():
    load_desktop_environment()
    port = int(os.environ.get("YC_AGENTS_DESKTOP_PORT", "8765"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
