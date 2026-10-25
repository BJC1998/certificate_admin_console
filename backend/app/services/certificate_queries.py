"""One filtering and sorting definition for list and complete CSV export."""
from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select

from app.database.tenant_session import TenantSession
from app.models import Certificate, Course, Learner, Tenant
from app.schemas.certificates import CertificateFilters


def selected_tenant(session: TenantSession) -> Tenant:
    tenant = session.scalar(select(Tenant).where(Tenant.id == session.tenant_id))
    if tenant is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return tenant


def certificate_statement(tenant_id: int, filters: CertificateFilters):
    statement = (select(Certificate.id, Certificate.tenant_id, Learner.name.label("learner_name"),
        Course.title.label("course_title"), Certificate.serial_number, Certificate.issued_at, Certificate.status)
        .join(Learner, and_(Learner.id == Certificate.learner_id, Learner.tenant_id == tenant_id))
        .join(Course, and_(Course.id == Certificate.course_id, Course.tenant_id == tenant_id))
        .where(Certificate.tenant_id == tenant_id))
    if filters.search:
        statement = statement.where(or_(Learner.name.icontains(filters.search, autoescape=True),
                                        Certificate.serial_number.icontains(filters.search, autoescape=True)))
    if filters.status is not None:
        statement = statement.where(Certificate.status == filters.status)
    return statement


def certificate_ordering(filters: CertificateFilters, timezone_name: str):
    columns = {"learner_name": Learner.name, "course_title": Course.title,
        "serial_number": Certificate.serial_number, "issued_at": Certificate.issued_at,
        "issue_date": func.tenant_local_date(Certificate.issued_at, timezone_name), "status": Certificate.status}
    column = columns[filters.sort_by]
    return (column.asc(), Certificate.id.asc()) if filters.sort_order == "asc" else (column.desc(), Certificate.id.desc())
