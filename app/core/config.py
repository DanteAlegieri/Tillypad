from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_reload: bool = True

    tillypad_sql_server: str = "26.187.75.193"
    tillypad_sql_port: int = 1433
    tillypad_sql_database: str = "TillypadSegment"
    tillypad_sql_user: str = ""
    tillypad_sql_password: str = ""
    tillypad_sql_driver: str = "ODBC Driver 18 for SQL Server"
    tillypad_sql_encrypt: str = "no"
    tillypad_sql_trust_certificate: str = "yes"
    tillypad_sql_timeout: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
