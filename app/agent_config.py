from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFIG_KEYS = (
    "TILLYPAD_SQL_SERVER",
    "TILLYPAD_SQL_PORT",
    "TILLYPAD_SQL_DATABASE",
    "TILLYPAD_SQL_USER",
    "TILLYPAD_SQL_PASSWORD",
    "TILLYPAD_SQL_DRIVER",
    "TILLYPAD_SQL_ENCRYPT",
    "TILLYPAD_SQL_TRUST_CERTIFICATE",
    "TILLYPAD_SQL_TIMEOUT",
    "TILLYPAD_AGENT_ID",
    "TILLYPAD_WS_GATEWAY_URL",
    "TILLYPAD_WS_API_KEY",
    "TILLYPAD_WS_HEARTBEAT",
    "TILLYPAD_WS_RECONNECT_MAX",
    "TILLYPAD_QUERY_CACHE_TTL",
    "TILLYPAD_QUERY_CACHE_MAX",
    "TILLYPAD_WS_COMPRESS_THRESHOLD",
    "TILLYPAD_CLOUD_SYNC_SECONDS",
    "RESTAURANTOS_LOCAL_WEB_HOST",
    "RESTAURANTOS_LOCAL_WEB_PORT",
)


@dataclass(frozen=True)
class AgentConfig:
    values: dict[str, str]
    source_path: Path

    def get(
        self,
        key: str,
        default: str = "",
    ) -> str:
        return self.values.get(key, default)

    @property
    def agent_id(self) -> str:
        return self.get("TILLYPAD_AGENT_ID", "KOMPUTER")

    @property
    def gateway_url(self) -> str:
        return self.get(
            "TILLYPAD_WS_GATEWAY_URL",
            "ws://127.0.0.1:8020/ws/agent",
        )

    @property
    def api_key(self) -> str:
        return self.get("TILLYPAD_WS_API_KEY")

    @property
    def local_web_host(self) -> str:
        return self.get(
            "RESTAURANTOS_LOCAL_WEB_HOST",
            "127.0.0.1",
        )

    @property
    def local_web_port(self) -> int:
        try:
            return int(
                self.get(
                    "RESTAURANTOS_LOCAL_WEB_PORT",
                    "8090",
                )
            )
        except ValueError:
            return 8090


_LOCK = threading.RLock()
_CURRENT: AgentConfig | None = None


def resolve_env_path() -> Path:
    explicit = os.environ.get("GASTRODOM_ENV_FILE")
    if explicit:
        return Path(explicit)

    data_dir = os.environ.get("RESTAURANTOS_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "agent.env"

    return Path.cwd() / "data" / "agent.env"


def parse_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}

    if not path.exists():
        return result

    for raw_line in path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    ).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key in CONFIG_KEYS:
            result[key] = value

    return result


def load_config(
    *,
    apply_to_environment: bool = True,
    force_reload: bool = False,
) -> AgentConfig:
    global _CURRENT

    with _LOCK:
        if _CURRENT is not None and not force_reload:
            return _CURRENT

        path = resolve_env_path()
        values = parse_env_file(path)

        for key in CONFIG_KEYS:
            if key not in values and key in os.environ:
                values[key] = os.environ[key]

        config = AgentConfig(
            values=values,
            source_path=path,
        )

        if apply_to_environment:
            for key, value in values.items():
                os.environ[key] = value

        _CURRENT = config
        return config


def reload_config() -> AgentConfig:
    return load_config(
        apply_to_environment=True,
        force_reload=True,
    )


def current_config() -> AgentConfig:
    return load_config()
