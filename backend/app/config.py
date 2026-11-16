from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "jobinsight"

    jwt_secret: str = "dev-only-secret-change-me-please-0123456789"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120

    admin_email: str | None = None
    admin_password: str | None = None
    pipeline_service_token: str | None = None
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    models_dir: str = "/opt/models"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
