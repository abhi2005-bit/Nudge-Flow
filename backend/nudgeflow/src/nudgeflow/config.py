
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the NudgeFlow API."""

    model_config = SettingsConfigDict(
        env_prefix="NUDGEFLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "NudgeFlow API"
    app_version: str = "0.1.0"
    environment: Literal["development", "testing", "production"] = "development"
    debug: bool = False
    database_url: str = "postgresql+psycopg://localhost:5432/nudgeflow"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    jwt_secret_key: SecretStr = SecretStr("")
    access_token_expire_minutes: int = Field(default=30, gt=0, le=1440)
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str | None = None
    llm_timeout_seconds: int = Field(default=15, gt=0, le=60)

    whatsapp_enabled: bool = False
    whatsapp_access_token: SecretStr = SecretStr("")
    whatsapp_phone_number_id: str | None = None
    whatsapp_api_version: str = "v25.0"

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.environment == "production":
            secret = self.jwt_secret_key.get_secret_value()
            if len(secret) < 32 or secret.lower().startswith(("replace-", "change-me")):
                raise ValueError(
                    "NUDGEFLOW_JWT_SECRET_KEY must contain at least 32 characters in production."
                )
            if self.debug:
                raise ValueError("NUDGEFLOW_DEBUG must be false in production.")
        if "*" in self.cors_origins:
            raise ValueError("NUDGEFLOW_CORS_ORIGINS must not contain a wildcard.")
        return self

settings = Settings()
