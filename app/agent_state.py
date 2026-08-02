from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentRuntimeState:
    def __init__(self) -> None:
        data_dir = Path(
            os.environ.get(
                "RESTAURANTOS_DATA_DIR",
                os.getcwd(),
            )
        )
        self.path = data_dir / "runtime_state.json"
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {
            "service_status": "starting",
            "gateway_status": "disconnected",
            "gateway_url": "",
            "agent_id": "",
            "sql_status": "unknown",
            "last_connected_at": None,
            "last_disconnected_at": None,
            "last_heartbeat_at": None,
            "last_query_at": None,
            "last_cloud_sync_at": None,
            "last_error": None,
            "reconnect_attempt": 0,
            "cache_entries": 0,
            "version": "",
            "hostname": os.environ.get("COMPUTERNAME", ""),
            "started_at": utc_now(),
        }
        self._load_existing()
        self.persist()

    def _load_existing(self) -> None:
        """
        История состояния полезна для диагностики, но идентификатор
        агента и Gateway всегда должны приходить из agent.env.
        """
        try:
            if self.path.exists():
                existing = json.loads(
                    self.path.read_text(encoding="utf-8")
                )
                if isinstance(existing, dict):
                    for key in (
                        "last_connected_at",
                        "last_disconnected_at",
                        "last_heartbeat_at",
                        "last_query_at",
                        "last_cloud_sync_at",
                        "last_error",
                    ):
                        if key in existing:
                            self._data[key] = existing[key]
                    self._data["started_at"] = utc_now()
        except Exception:
            pass

    def update(self, **values: Any) -> None:
        with self._lock:
            self._data.update(values)
            self._data["updated_at"] = utc_now()
            self.persist()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def persist(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    self._data,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)


_STATE: AgentRuntimeState | None = None
_STATE_LOCK = threading.Lock()


def get_runtime_state() -> AgentRuntimeState:
    global _STATE
    with _STATE_LOCK:
        if _STATE is None:
            _STATE = AgentRuntimeState()
        return _STATE
