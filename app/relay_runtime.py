from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


SERVICE_NAME = "GastrodomRelayAgent"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8010


def program_data_dir() -> Path:
    root = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    return Path(root) / "Gastrodom" / "RelayAgent"


def configure_runtime_environment() -> Path:
    data_dir = program_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = data_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    env_file = data_dir / "agent.env"
    os.environ.setdefault("GASTRODOM_ENV_FILE", str(env_file))
    os.environ.setdefault("TILLYPAD_RELAY_CACHE_DIR", str(cache_dir))

    os.chdir(data_dir)
    return data_dir


def run_agent() -> None:
    configure_runtime_environment()

    host = os.environ.get("RELAY_AGENT_HOST", DEFAULT_HOST)
    port = int(os.environ.get("RELAY_AGENT_PORT", str(DEFAULT_PORT)))

    uvicorn.run(
        "app.relay_agent:app",
        host=host,
        port=port,
        reload=False,
        access_log=False,
        log_level="info",
    )


if __name__ == "__main__":
    run_agent()
