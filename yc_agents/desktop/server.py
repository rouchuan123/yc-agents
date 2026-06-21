import os

import uvicorn

from yc_agents.desktop.app import create_app


def main():
    port = int(os.environ.get("YC_AGENTS_DESKTOP_PORT", "8765"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
