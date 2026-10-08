"""Typed, 12-factor configuration for ACIP (docs/01 §6, docs/07 §2).

A single ``Settings`` class reads every environment variable documented in
docs/07 §2 with the locked defaults. All services import this instead of reading
``os.environ`` directly, so config is centralized and validated once.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform configuration, populated from the environment.

    Defaults mirror docs/07 §2 so the stack boots with no ``.env`` present.
    Secrets (DB passwords, ADC key path) are provided via env only.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- messaging ---
    kafka_bootstrap: str = Field(default="kafka:9092", alias="KAFKA_BOOTSTRAP")

    # --- stores ---
    neo4j_uri: str = Field(default="bolt://neo4j:7687", alias="NEO4J_URI")
    neo4j_auth: str = Field(default="neo4j/password", alias="NEO4J_AUTH")
    postgres_dsn: str = Field(
        default="postgresql://acip:acip@postgres:5432/acip", alias="POSTGRES_DSN"
    )
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

    # --- llm ---
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-1.5-pro", alias="LLM_MODEL")
    llm_fallback_provider: str = Field(default="mock", alias="LLM_FALLBACK_PROVIDER")
    google_application_credentials: str = Field(
        default="/secrets/adc.json", alias="GOOGLE_APPLICATION_CREDENTIALS"
    )

    # --- decisioning ---
    decision_deadline_ms: int = Field(default=800, alias="DECISION_DEADLINE_MS")
    fraud_block_threshold: float = Field(default=0.85, alias="FRAUD_BLOCK_THRESHOLD")
    approve_max: float = Field(default=0.35, alias="APPROVE_MAX")
    challenge_max: float = Field(default=0.70, alias="CHALLENGE_MAX")
    w_risk: float = Field(default=0.5, alias="W_RISK")
    w_fraud: float = Field(default=0.5, alias="W_FRAUD")

    # --- representation + methods ---
    representation_version: int = Field(default=1, alias="REPRESENTATION_VERSION")
    enabled_method_types: list[str] = Field(
        default_factory=lambda: ["card", "upi", "netbanking", "wallet", "cod"],
        alias="ENABLED_METHOD_TYPES",
    )

    # --- processor sim ---
    sim_approval_rate: float = Field(default=0.9, alias="SIM_APPROVAL_RATE")
    sim_latency_ms: int = Field(default=40, alias="SIM_LATENCY_MS")

    @field_validator("enabled_method_types", mode="before")
    @classmethod
    def _split_method_types(cls, value: object) -> object:
        """Parse the comma-separated ``ENABLED_METHOD_TYPES`` env string into a list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


def get_settings() -> Settings:
    """Return a freshly loaded ``Settings`` instance.

    Not cached, so tests can override the environment between calls.
    """
    return Settings()
