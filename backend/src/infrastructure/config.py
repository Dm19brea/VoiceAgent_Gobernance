import os

from pydantic_settings import BaseSettings, SettingsConfigDict


def _dotenv_file() -> str | None:
    """Select the developer dotenv file unless the process disables it explicitly."""
    if os.getenv("GOVERNANCE_DISABLE_DOTENV") == "1":
        return None
    return ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_dotenv_file(), extra="ignore")

    database_url: str = "postgresql+asyncpg://governance:governance@localhost:5432/governance"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = (
        "http://localhost:3000,https://optimistic-stillness-production-cf18.up.railway.app"
    )
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 10.0
    vapi_api_key: str = ""
    vapi_base_url: str = "https://api.vapi.ai"
    vapi_timeout_seconds: float = 10.0
    vapi_webhook_secret: str = ""
    jwt_secret: str = ""
    auth_cookie_secure: bool | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        """Allowed dashboard origins, from a comma-separated ``CORS_ORIGINS``."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def async_database_url(self) -> str:
        """Normalise a plain ``postgresql://`` URL (e.g. Railway's) to asyncpg."""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


settings = Settings()
