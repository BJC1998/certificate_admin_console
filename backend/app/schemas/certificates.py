from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CertificateStatus

SortField = Literal["learner_name", "course_title", "serial_number", "issued_at", "status"]
SortOrder = Literal["asc", "desc"]


class CertificateQuery(BaseModel):
    search: str = Field(default="", max_length=200)
    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(default=10, ge=1, le=100)
    sort_by: SortField = "issued_at"
    sort_order: SortOrder = "desc"

    @field_validator("search")
    @classmethod
    def trim_search(cls, value: str) -> str:
        return value.strip()


class TenantOption(BaseModel):
    id: int
    name: str
    timezone: str


class CertificateRecord(BaseModel):
    id: int
    tenant_id: int
    learner_name: str
    course_title: str
    serial_number: str
    issued_at: datetime
    status: CertificateStatus


class CertificatePage(BaseModel):
    records: list[CertificateRecord]
    total: int
    page: int
    page_size: int
    total_pages: int
    tenant_id: int
    tenant_timezone: str


class CertificateDetail(CertificateRecord):
    learner_id: int
    course_id: int
    tenant_name: str
    tenant_timezone: str


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RevokeResponse(BaseModel):
    certificate: CertificateDetail
    changed: bool
