"""Public demo selector metadata only; never expose business data across tenants."""
from fastapi import APIRouter
from sqlalchemy import select

from app.database.engine import engine
from app.models import Tenant
from app.schemas.certificates import TenantOption

router = APIRouter(prefix="/api/tenants", tags=["demo tenants"])


@router.get("", response_model=list[TenantOption])
def tenant_options() -> list[TenantOption]:
    # Explicit root-metadata discovery exception for the unauthenticated demo selector.
    with engine.connect() as connection:
        rows = connection.execute(select(Tenant.id, Tenant.name, Tenant.timezone).order_by(Tenant.id))
        return [TenantOption(id=row.id, name=row.name, timezone=row.timezone) for row in rows]
