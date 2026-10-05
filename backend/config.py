from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/resq.db"
    jwt_secret: str = "development-only-resq-kerala-change-this-secret-before-deployment"
    demo_mode: bool = True
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "gemma4:e4b-it-q4_K_M"
    ai_timeout_seconds: int = 120
    ai_enabled: bool = True
    geocoding_enabled: bool = Field(default=True, validation_alias="RESQ_GEOCODING_ENABLED")
    geocoding_url: str = Field(default="https://nominatim.openstreetmap.org/search", validation_alias="RESQ_GEOCODING_URL")
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    upload_dir: str = "data/uploads"
    frontend_url: str = "http://localhost:5173"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True
    payment_provider: str = "offline"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    @field_validator("jwt_secret")
    @classmethod
    def strong_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        return value


@lru_cache
def get_settings() -> Settings:
    config = Settings()
    if not config.demo_mode and config.jwt_secret.startswith(("development-only", "local-resq")):
        raise ValueError("Set a private JWT_SECRET before disabling DEMO_MODE")
    return config


settings = get_settings()
