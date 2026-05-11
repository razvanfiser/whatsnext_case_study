"""Application settings loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536


@lru_cache
def get_settings() -> Settings:
    return Settings()
