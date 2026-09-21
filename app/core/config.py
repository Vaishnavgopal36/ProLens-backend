from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MIGRATION_DATABASE_URL: str
    APP_DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # Supabase Storage, S3-compatible endpoint
    # (Dashboard -> Storage -> S3 Connection).
    SUPABASE_S3_ENDPOINT: str
    SUPABASE_S3_REGION: str = "us-east-1"
    SUPABASE_S3_ACCESS_KEY_ID: str
    SUPABASE_S3_SECRET_ACCESS_KEY: str
    SUPABASE_S3_BUCKET: str = "attachments"
    ATTACHMENT_URL_EXPIRE_SECONDS: int = 300
    ATTACHMENT_MAX_SIZE_BYTES: int = 25 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
