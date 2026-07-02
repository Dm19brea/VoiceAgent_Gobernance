from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://governance:governance@localhost:5432/governance"

    @property
    def async_database_url(self) -> str:
        """Normalise a plain ``postgresql://`` URL (e.g. Railway's) to asyncpg."""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


settings = Settings()
