from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    mongo_host: str = "mongodb://localhost:27017/"
    mongo_db: str = "vandalizer"
    redis_host: str = "localhost"
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 60
    upload_dir: str = "../app/static/uploads"
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"
    insight_endpoint: str = ""
    chromadb_persist_dir: str = "../app/static/db"
    max_context_length: int = 100000
    max_upload_size_mb: int = 500

    # Observability
    sentry_dsn: str = ""
    log_format: str = "json"  # "json" for structured logging, "text" for human-readable

    # Email provider: "smtp" or "resend"
    email_provider: str = "smtp"

    # SMTP email settings
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False  # Implicit TLS (port 465)
    smtp_start_tls: bool = True  # STARTTLS upgrade (port 587)
    smtp_from_email: str = ""
    smtp_from_name: str = "Vandalizer"

    # Resend email settings (used when email_provider=resend)
    resend_api_key: str = ""
    resend_from_email: str = ""
    resend_from_name: str = "Vandalizer"

    # Encryption key for sensitive config values (API keys) stored in MongoDB.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    config_encryption_key: str = ""

    # File storage backend ("local" or "s3")
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_endpoint_url: str | None = None

    # Trial / demo system (disabled by default for self-hosters)
    enable_trial_system: bool = False

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        # Resolve relative paths against the backend directory (parent of app/)
        # so Celery workers and FastAPI resolve identically regardless of cwd.
        backend_dir = Path(__file__).resolve().parent.parent
        upload = Path(self.upload_dir)
        chroma = Path(self.chromadb_persist_dir)
        self.upload_dir = str(upload if upload.is_absolute() else (backend_dir / upload).resolve())
        self.chromadb_persist_dir = str(chroma if chroma.is_absolute() else (backend_dir / chroma).resolve())
        # Ensure directories exist on startup
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        Path(self.chromadb_persist_dir).mkdir(parents=True, exist_ok=True)
        return self

    @model_validator(mode="after")
    def _check_jwt_secret(self) -> "Settings":
        if self.jwt_secret_key == "change-me" and self.environment != "development":
            raise ValueError(
                "jwt_secret_key must be changed from the default 'change-me' "
                "in non-development environments. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"
