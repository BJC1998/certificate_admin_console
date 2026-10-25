"""SQLite engine factory for request sessions and explicit maintenance tools."""
from sqlite3 import Connection

from sqlalchemy import Engine, create_engine, event

from app.core.config import settings
from app.core.timezones import tenant_local_date


def create_sqlite_engine(database_url: str, **kwargs: object) -> Engine:
    if not database_url.startswith("sqlite:"):
        raise ValueError("This application requires a SQLite DATABASE_URL.")
    sqlite_engine = create_engine(database_url, connect_args={"check_same_thread": False}, **kwargs)

    @event.listens_for(sqlite_engine, "connect")
    def enable_foreign_keys(connection: Connection, _connection_record: object) -> None:
        connection.create_function("tenant_local_date", 2, tenant_local_date, deterministic=True)
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return sqlite_engine


engine = create_sqlite_engine(settings.database_url)
