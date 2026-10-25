"""Tenant-scoped request sessions; plain Sessions are for maintenance tools only."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import sessionmaker

from app.core.tenant import TenantContext, get_tenant_context
from app.database.engine import engine
from app.database.tenant_session import TenantSession

SessionLocal = sessionmaker(bind=engine, class_=TenantSession, autoflush=False, expire_on_commit=False)


def get_session(
    tenant: Annotated[TenantContext, Depends(get_tenant_context)],
) -> Generator[TenantSession, None, None]:
    """Resolve demo tenant context first. Services own explicit transactions."""
    with SessionLocal(tenant_id=tenant.id) as session:
        yield session
