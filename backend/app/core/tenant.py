"""Demo tenant selection only: this header does NOT authenticate or authorize users."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException
from sqlalchemy import select

from app.database.engine import engine
from app.models import Tenant


@dataclass(frozen=True)
class TenantContext:
    id: int


def get_tenant_context(
    x_tenant_id: Annotated[int, Header(gt=0, description="Demo tenant selection; not authentication")],
) -> TenantContext:
    # Exact root-tenant lookup; never a lookup of another tenant's business data.
    with engine.connect() as connection:
        tenant_id = connection.scalar(select(Tenant.id).where(Tenant.id == x_tenant_id))
    if tenant_id is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return TenantContext(id=tenant_id)
