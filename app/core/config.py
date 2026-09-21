from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MIGRATION_DATABASE_URL: str
    APP_DATABASE_URL: str

    APP_TIMEZONE: str = "Asia/Kolkata"

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    PUBLIC_BASE_URL: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
