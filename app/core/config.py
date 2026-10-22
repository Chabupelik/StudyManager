from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str = ""
    group_id: str = ""

    vk_token: str | None = None
    vk_group_id: int = 0
    vk_chat_peer_id: int = 0
    vk_api_version: str = "5.199"
    vk_protected_key: str = ""

    developer_id: int = 620159705

    admin_ids: str = ""
    curator_id: int = 0

    logs_secret_key: str = ""
    internal_secret: str = ""

    api_keys: str = ""

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 30

    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "postgres"
    postgres_host: str = "db"
    postgres_port: int = 5432

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    show_docs: bool = False

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def admin_ids_list(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    @property
    def api_keys_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(";") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
