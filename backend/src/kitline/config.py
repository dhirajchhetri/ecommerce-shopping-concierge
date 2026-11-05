"""Runtime settings.

Environment variables use the KITLINE_ prefix. KITLINE_MODE=offline is the
default and does not call AWS.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KITLINE_", extra="ignore")

    mode: Literal["offline", "bedrock"] = "offline"
    bedrock_model_id: str = "global.anthropic.claude-sonnet-4-6"
    bedrock_region: str = "us-west-2"
    embeddings: Literal["local", "bedrock"] = "local"
    vector_store: Literal["local", "pgvector", "opensearch"] = "local"
    database_url: str | None = None
    opensearch_endpoint: str | None = None
    opensearch_index: str = "kitline-products"
    session_store: Literal["memory", "file", "dynamodb"] = "memory"
    session_dir: str = ".data/sessions"
    session_table: str = "kitline-sessions"
    aws_region: str = "us-west-2"
    max_attempts: int = 2
    stub_fault: Literal["honest", "bad-sku-once", "incompatible-once", "always-bad"] = "honest"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
