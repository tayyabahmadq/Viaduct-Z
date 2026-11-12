"""Database engine and session plumbing."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


def _normalize(url: str) -> str:
    """Accept the URLs hosted providers hand out (Render, Neon, Heroku)."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


_url = _normalize(get_settings().database_url)
_is_sqlite = _url.startswith("sqlite")

engine = create_engine(
    _url,
    pool_pre_ping=True,
    pool_recycle=300,
    future=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
