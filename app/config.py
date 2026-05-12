from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_dsn: PostgresDsn
    mongo_uri: str
    mongo_db: str = "homework"
    redis_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "homework-attachments"
    proxy_url: str | None = None
    gemini_api_key: str | None = None
    stats_service_url: str | None = None
    stats_module_name: str = "homework-widget"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
