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
    jwt_secret: str = Field(
        default="dev-jwt-secret-change-me-32b-min!!",
        validation_alias="JWT_SECRET",
    )
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=60, validation_alias="JWT_EXPIRE_MINUTES")
    # url-safe base64 32-byte key; override in real deploys
    secrets_fernet_key: str = Field(
        default="WrU8g7fNF5VR7r_n03I_RXkGAFBhYx0I7WSeeFUeJw4=",
        validation_alias="SECRETS_FERNET_KEY",
    )
    seed_admin_email: str = Field(default="admin@brokerbridge.local", validation_alias="SEED_ADMIN_EMAIL")
    seed_admin_password: str = Field(default="admin123!", validation_alias="SEED_ADMIN_PASSWORD")
    infra_provider: str = Field(default="mock", validation_alias="INFRA_PROVIDER")
    broker_provider: str = Field(default="mock", validation_alias="BROKER_PROVIDER")
    lock_provider: str = Field(default="memory", validation_alias="LOCK_PROVIDER")
    session_provider: str = Field(default="memory", validation_alias="SESSION_PROVIDER")
    rate_limit_provider: str = Field(default="memory", validation_alias="RATE_LIMIT_PROVIDER")
    # Event bus bootstrap (FR-21 cold start). Overridden by active provider_configs kind=event.
    event_provider: str = Field(default="memory", validation_alias="EVENT_PROVIDER")
    kafka_bootstrap_servers: str = Field(default="", validation_alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_security_protocol: str = Field(default="PLAINTEXT", validation_alias="KAFKA_SECURITY_PROTOCOL")
    kafka_sasl_mechanism: str = Field(default="", validation_alias="KAFKA_SASL_MECHANISM")
    kafka_username: str = Field(default="", validation_alias="KAFKA_USERNAME")
    kafka_password: str = Field(default="", validation_alias="KAFKA_PASSWORD")
    kafka_ssl: bool = Field(default=False, validation_alias="KAFKA_SSL")
    kafka_topic_prefix: str = Field(default="brokerbridge", validation_alias="KAFKA_TOPIC_PREFIX")
    kafka_consumer_group: str = Field(default="brokerbridge-lab", validation_alias="KAFKA_CONSUMER_GROUP")
    max_inflight_orders: int = Field(default=100, validation_alias="MAX_INFLIGHT_ORDERS")
    latency_budget_ms: float = Field(default=500.0, validation_alias="LATENCY_BUDGET_MS")
    ip_reuse_cooldown_hours: int = Field(default=24, validation_alias="IP_REUSE_COOLDOWN_HOURS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
