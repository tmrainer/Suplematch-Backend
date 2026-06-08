from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.db.models import Base


def _validate_postgres_url(database_url: str) -> None:
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")):
        raise ValueError("DATABASE_URL debe apuntar a PostgreSQL para la base relacional.")


def create_db_engine(database_url: str | None = None) -> Engine:
    url = database_url or settings.DATABASE_URL
    _validate_postgres_url(url)
    return create_engine(
        url,
        echo=settings.DB_ECHO,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


engine = create_db_engine()


def create_all_tables() -> None:
    Base.metadata.create_all(bind=engine)
