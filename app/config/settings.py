from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="dev", validation_alias="APP_ENV")
    app_name: str = Field(default="BrokerBridge API", validation_alias="APP_NAME")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    docs_enabled: bool = Field(default=True, validation_alias="DOCS_ENABLED")
    admin_ui_enabled: bool = Field(default=True, validation_alias="ADMIN_UI_ENABLED")
    database_url: str = Field(
        default="postgresql+asyncpg://brokerbridge:brokerbridge@localhost:5432/brokerbridge",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    redpanda_brokers: str = Field(
        default="localhost:19092",
        validation_alias="REDPANDA_BROKERS",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
