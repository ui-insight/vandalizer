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
    insight_endpoint: str = "https://mindrouter-api.nkn.uidaho.edu/v1"
    chromadb_persist_dir: str = "data/chromadb"
    max_context_length: int = 100000

    @property
    def is_production(self) -> bool:
        return self.environment == "production"
