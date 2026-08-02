import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings
from app.db.sql_server import SqlServer


class ConnectionService:
    def status(self) -> dict[str, Any]:
        s = get_settings()
        mode = s.tillypad_connection_mode.strip().lower()
        started = time.perf_counter()
        if mode == "relay":
            headers = {"Accept": "application/json"}
            if s.tillypad_relay_api_key:
                headers["X-Relay-Key"] = s.tillypad_relay_api_key
            request = Request(
                s.tillypad_relay_url.rstrip("/") + "/v1/health",
                headers=headers,
                method="GET",
            )
            try:
                with urlopen(request, timeout=s.tillypad_relay_timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return {
                    "ok": True,
                    "mode": "relay",
                    "label": "Промежуточный сервис",
                    "database": payload.get("database"),
                    "latency_ms": payload.get("latency_ms"),
                    "url": s.tillypad_relay_url,
                }
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                return {
                    "ok": False,
                    "mode": "relay",
                    "label": "Промежуточный сервис",
                    "error": str(exc),
                    "url": s.tillypad_relay_url,
                }
        try:
            info = SqlServer().info()
            return {
                "ok": True,
                "mode": "direct",
                "label": "Прямое подключение",
                "database": info.database_name,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "url": s.tillypad_sql_server,
            }
        except Exception as exc:
            return {
                "ok": False,
                "mode": "direct",
                "label": "Прямое подключение",
                "error": str(exc),
                "url": s.tillypad_sql_server,
            }
