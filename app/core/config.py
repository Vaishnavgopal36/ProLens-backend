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

    # Browser origins allowed to call the API with cookies (CORS).
    CORS_ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]
    FRONTEND_BASE_URL: str = "http://localhost:5173"

    PASSWORD_MIN_LENGTH: int = 8
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300

    # Email delivery (worker). SMTP_HOST unset -> emails are logged, not sent.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    EMAIL_FROM: str = "ProLens <no-reply@prolens.local>"

    # Outbox worker (Postgres-backed queue).
    OUTBOX_POLL_INTERVAL_SECONDS: float = 2.0
    OUTBOX_BATCH_SIZE: int = 10
    OUTBOX_MAX_ATTEMPTS: int = 5
    OUTBOX_RETRY_BASE_SECONDS: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
