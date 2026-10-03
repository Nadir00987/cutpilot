"""CutPilot AI backend configuration.

Everything comes from the environment (or a local .env file). No secrets in code.
See backend/.env.example for the full documented list.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "CutPilot AI"
    environment: str = "dev"

    # sqlite:///./cutpilot.db locally; postgres via DATABASE_URL in compose
    database_url: str = "sqlite:///./cutpilot.db"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-only-insecure-secret-change-me"
    access_token_minutes: int = 30
    refresh_token_days: int = 7

    storage_dir: str = "storage"
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    frontend_url: str = "http://localhost:3000"

    # Billing (Stripe). Unset => checkout/webhook run in stub mode.
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_starter: str | None = None
    stripe_price_pro: str | None = None
    stripe_price_studio: str | None = None

    # Stock media
    pexels_api_key: str | None = None
    pixabay_api_key: str | None = None

    # Vision / LLM (OpenAI-compatible endpoints, Worker B's pipeline reads these)
    vision_api_url: str | None = None
    vision_api_key: str | None = None
    vision_model: str | None = None
    llm_api_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    # TTS (optional voiceover)
    tts_provider: str | None = None
    tts_api_key: str | None = None
    tts_api_url: str | None = None

    email_provider: str = "console"  # console | smtp (smtp not wired yet)

    silence_threshold_sec: float = 0.8
    credits_per_minute: float = 1.0
    whisper_model: str = "base"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Absolute repo paths derived from this file, not from cwd.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent  # ~/workspace/cutpilot-ai


def storage_root() -> Path:
    """Shared media root: <repo>/storage (same tree Worker B/C use via
    app.services.common.storage_dir)."""
    p = Path(settings.storage_dir)
    return p if p.is_absolute() else (REPO_ROOT / p)
