from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    tillypad_token: str = ""
    tillypad_api_url: str = "https://api.tillypad.online/_v1.0/Request.php"
    tillypad_timeout: int = 120

    database_url: str = "sqlite:///./data/tillypad.db"

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_reload: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
