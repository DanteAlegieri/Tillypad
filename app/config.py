import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_url: str = os.getenv(
        "TILLYPAD_API_URL",
        "https://api.tillypad.online/_v1.0/Request.php",
    )
    token: str = os.getenv("TILLYPAD_TOKEN", "").strip()
    timeout: int = int(os.getenv("TILLYPAD_TIMEOUT", "120"))
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = int(os.getenv("APP_PORT", "8000"))


settings = Settings()
