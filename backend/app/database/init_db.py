"""Explicit schema initialization: python -m app.database.init_db (from backend)."""
from sqlalchemy import Engine

from app.database.engine import engine
from app.models import Base


def initialize_database(bind: Engine = engine) -> None:
    Base.metadata.create_all(bind)


if __name__ == "__main__":
    initialize_database()
    print("Database tables initialized. Existing tables/data were preserved.")
