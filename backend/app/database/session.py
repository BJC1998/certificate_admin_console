"""Lazy SQLite engine and session lifecycle; importing this creates no database."""

from collections.abc import Generator
from sqlite3 import Connection

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

if not settings.database_url.startswith("sqlite:"):
    raise ValueError("This application requires a SQLite DATABASE_URL.")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def enable_foreign_keys(connection: Connection, _connection_record: object) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """Yield one session; services will own explicit write transactions."""
    with SessionLocal() as session:
        yield session
