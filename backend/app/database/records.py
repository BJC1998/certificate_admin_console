"""Shared scoped single-record lookup; no certificate business operations."""
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import select

from app.database.tenant_session import TenantSession
from app.models import TenantOwned

Record = TypeVar("Record", bound=TenantOwned)


def get_tenant_record(session: TenantSession, model: type[Record], record_id: int) -> Record:
    record = session.scalar(select(model).where(model.id == record_id, model.tenant_id == session.tenant_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return record
