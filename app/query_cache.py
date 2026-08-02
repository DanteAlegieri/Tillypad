from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    value: dict[str, Any]
    expires_at: float


class QueryCache:
    def __init__(
        self,
        default_ttl_seconds: int = 45,
        max_entries: int = 256,
    ) -> None:
        self.default_ttl_seconds = max(0, default_ttl_seconds)
        self.max_entries = max(1, max_entries)
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    @staticmethod
    def build_key(
        query_name: str,
        parameters: dict[str, Any],
    ) -> str:
        normalized = json.dumps(
            {
                "query_name": query_name,
                "parameters": parameters,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            return dict(entry.value)

    def set(
        self,
        key: str,
        value: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        ttl = (
            self.default_ttl_seconds
            if ttl_seconds is None
            else max(0, ttl_seconds)
        )
        if ttl == 0:
            return

        with self._lock:
            self._remove_expired_locked()
            if len(self._entries) >= self.max_entries:
                oldest_key = min(
                    self._entries,
                    key=lambda item: self._entries[item].expires_at,
                )
                self._entries.pop(oldest_key, None)

            self._entries[key] = CacheEntry(
                value=dict(value),
                expires_at=time.monotonic() + ttl,
            )

    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            return count

    def size(self) -> int:
        with self._lock:
            self._remove_expired_locked()
            return len(self._entries)

    def _remove_expired_locked(self) -> None:
        now = time.monotonic()
        expired = [
            key
            for key, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for key in expired:
            self._entries.pop(key, None)
