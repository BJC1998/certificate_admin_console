"""Function-scoped pytest fixtures; never connect test endpoints to the demo database."""
import pytest
from fastapi.testclient import TestClient

from app.database.engine import create_sqlite_engine
from app.database.seed import seed_database
from app.database.tenant_session import TenantSession
from app.main import app


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    engine = create_sqlite_engine(f"sqlite:///{(tmp_path / 'core-tests.db').as_posix()}")
    seed_database(engine)
    monkeypatch.setattr("app.core.tenant.engine", engine)
    monkeypatch.setattr("app.routers.tenants.engine", engine)
    monkeypatch.setattr("app.database.session.SessionLocal", lambda **kwargs: TenantSession(engine, **kwargs))
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def api_client(isolated_db):
    with TestClient(app) as client:
        yield client
