from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    mongo_host: str = "mongodb://localhost:27017/"
    mongo_db: str = "osp"
    redis_host: str = "localhost"
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 60
    upload_dir: str = "../app/static/uploads"
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"
    openai_api_key: str = ""
    insight_endpoint: str = ""
    chromadb_persist_dir: str = "../app/static/db"
    max_context_length: int = 100000
    max_upload_size_mb: int = 500

    # Observability
    sentry_dsn: str = ""
    log_format: str = "json"  # "json" for structured logging, "text" for human-readable

    # SMTP email settings
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_email: str = ""
    smtp_from_name: str = "Vandalizer"

    @model_validator(mode="after")
    def _check_jwt_secret(self) -> "Settings":
        if self.jwt_secret_key == "change-me" and self.environment != "development":
            raise ValueError(
                "jwt_secret_key must be changed from the default 'change-me' "
                "in non-development environments. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return self

    @model_validator(mode="after")
    def _check_openai_api_key(self) -> "Settings":
        if not self.openai_api_key and self.environment not in ("development", "test"):
            raise ValueError(
                "openai_api_key must be set in non-development/test environments. "
                "Set the OPENAI_API_KEY environment variable."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"
