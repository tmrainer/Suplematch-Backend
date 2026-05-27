from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "SupleMatch API"
    APP_VERSION: str = "0.1.0"

    CORS_ORIGINS: list[str] = ["*"]

    class Config:
        env_file = ".env"


settings = Settings()
