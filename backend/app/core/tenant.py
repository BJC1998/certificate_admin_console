"""Demo tenant selection only: this header does NOT authenticate or authorize users."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database.engine import engine
from app.models import Tenant


@dataclass(frozen=True)
class TenantContext:
    id: int


def resolve_tenant(tenant_id: int) -> TenantContext:
    # Exact root-tenant lookup; never a lookup of another tenant's business data.
    try:
        with engine.connect() as connection:
            tenant_id = connection.scalar(select(Tenant.id).where(Tenant.id == tenant_id))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable. Please retry.",
                            headers={"Retry-After": "1"}) from None
    if tenant_id is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return TenantContext(id=tenant_id)


def get_tenant_context(
    x_tenant_id: Annotated[int, Header(gt=0, le=9_223_372_036_854_775_807, description="Demo tenant selection; not authentication")],
) -> TenantContext:
    return resolve_tenant(x_tenant_id)


def get_path_tenant_context(
    tenant_id: Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)],
    x_tenant_id: Annotated[int | None, Header(gt=0, le=9_223_372_036_854_775_807)] = None,
) -> TenantContext:
    """URL selects the demo tenant; an optional header must agree with it."""
    if x_tenant_id is not None and tenant_id != x_tenant_id:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resolve_tenant(tenant_id)
