from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_token: str = ""
    discord_channel_id: int
    database_url: str = Field(alias="DATABASE_URL")
    poll_interval_seconds: int = 600
    request_timeout_seconds: float = 20.0
    max_items_per_source: int = 10
    user_agent: str = "DiscordFeedBot/0.1"
    db_create_tables: bool = True
    sources_file: Path = Path("sources.yaml")


@lru_cache
def get_settings() -> Settings:
    return Settings()
