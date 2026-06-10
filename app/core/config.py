from pathlib import Path

from pydantic_settings import SettingsConfigDict
from pydantic_settings import BaseSettings
from pydantic import model_validator


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "SupleMatch API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    CORS_ORIGINS: list[str] = ["*"]
    DATABASE_URL: str = "postgresql+psycopg://suplematch:suplematch@localhost:5432/suplematch"
    DB_ECHO: bool = False
    JWT_SECRET_KEY: str = "change-me-local-dev-only"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    PASSWORD_RESET_TOKEN_TTL_MINUTES: int = 30
    PASSWORD_RESET_RETURN_TOKEN: bool = False
    PUBLIC_FRONTEND_URL: str = "http://localhost:5173"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_USE_TLS: bool = True
    MODEL_DIR: Path = BASE_DIR / "app/ml/runtime"
    FEEDBACK_DB_PATH: Path = BASE_DIR / "app/ml/runtime/feedback.sqlite3"
    DIGEMID_CSV_PATH: Path = BASE_DIR / "data/raw/csv/digemid_limpio.csv"
    PRODUCT_COMPONENTS_CSV_PATH: Path = BASE_DIR / "data/training/modelo2/product_components.csv"
    APPROVED_CATALOG_PATH: Path = BASE_DIR / "data/catalog/approved_catalog.csv"
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    @model_validator(mode="after")
    def validate_deployment_safety(self):
        env = self.ENVIRONMENT.lower()
        if env in {"staging", "production", "prod"}:
            if self.JWT_SECRET_KEY == "change-me-local-dev-only" or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("JWT_SECRET_KEY debe ser fuerte y configurado por entorno en staging/prod.")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("CORS_ORIGINS no puede incluir '*' en staging/prod.")
            if self.PASSWORD_RESET_RETURN_TOKEN:
                raise ValueError("PASSWORD_RESET_RETURN_TOKEN no puede estar activo en staging/prod.")
        return self


settings = Settings()
