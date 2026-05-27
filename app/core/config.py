from pathlib import Path

from pydantic_settings import SettingsConfigDict
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    APP_NAME: str = "SupleMatch API"
    APP_VERSION: str = "0.1.0"

    CORS_ORIGINS: list[str] = ["*"]
    MODEL_DIR: Path = BASE_DIR / "app/ml/runtime"
    FEEDBACK_DB_PATH: Path = BASE_DIR / "app/ml/runtime/feedback.sqlite3"
    DIGEMID_CSV_PATH: Path = BASE_DIR / "digemid_limpio.csv"
    PRODUCT_COMPONENTS_CSV_PATH: Path = BASE_DIR / "product_components.csv"
    APPROVED_CATALOG_PATH: Path = BASE_DIR / "data/catalog/approved_catalog.csv"


settings = Settings()
