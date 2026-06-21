import uvicorn

from yc_agents.desktop.app import create_app


def main():
    uvicorn.run(create_app(), host="127.0.0.1", port=8765, log_level="info")


if __name__ == "__main__":
    main()
