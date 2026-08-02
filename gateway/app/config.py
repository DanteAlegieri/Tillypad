from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str = os.environ.get("GATEWAY_HOST", "0.0.0.0")
    port: int = int(os.environ.get("GATEWAY_PORT", "8020"))
    database_path: Path = Path(
        os.environ.get(
            "GATEWAY_DB_PATH",
            str(Path(__file__).resolve().parents[1] / "data" / "gateway.db"),
        )
    )
    admin_token: str = os.environ.get(
        "GATEWAY_ADMIN_TOKEN",
        "change-me-admin-token",
    )
    request_timeout_seconds: int = int(
        os.environ.get("GATEWAY_REQUEST_TIMEOUT", "30")
    )


settings = Settings()
