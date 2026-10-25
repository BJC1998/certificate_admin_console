"""Read-only server-side certificate search, pagination and allowlisted sorting."""
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select

from app.database.tenant_session import TenantSession
from app.models import Certificate, Course, Learner, Tenant
from app.schemas.certificates import CertificatePage, CertificateQuery, CertificateRecord


def list_certificates(session: TenantSession, query: CertificateQuery) -> CertificatePage:
    tenant_id = session.tenant_id
    tenant = session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    base = (select(Certificate, Learner.name, Course.title)
            .join(Learner, and_(Learner.id == Certificate.learner_id, Learner.tenant_id == tenant_id))
            .join(Course, and_(Course.id == Certificate.course_id, Course.tenant_id == tenant_id))
            .where(Certificate.tenant_id == tenant_id))
    if query.search:
        # Treat %, _ and the escape character as literal user text, not LIKE wildcards.
        base = base.where(or_(Learner.name.icontains(query.search, autoescape=True),
                              Certificate.serial_number.icontains(query.search, autoescape=True)))
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    sort_columns = {
        "learner_name": Learner.name,
        "course_title": Course.title,
        "serial_number": Certificate.serial_number,
        "issued_at": Certificate.issued_at,
        "status": Certificate.status,
    }
    column = sort_columns[query.sort_by]
    ordering = (column.asc(), Certificate.id.asc()) if query.sort_order == "asc" else (column.desc(), Certificate.id.desc())
    rows = session.execute(base.order_by(*ordering).offset((query.page - 1) * query.page_size).limit(query.page_size)).all()
    timezone = ZoneInfo(tenant.timezone)
    records = [CertificateRecord(
        id=certificate.id, tenant_id=tenant_id, learner_name=learner_name, course_title=course_title,
        serial_number=certificate.serial_number, issued_at=certificate.issued_at.astimezone(timezone), status=certificate.status,
    ) for certificate, learner_name, course_title in rows]
    return CertificatePage(records=records, total=total, page=query.page, page_size=query.page_size,
                           total_pages=(total + query.page_size - 1) // query.page_size,
                           tenant_id=tenant_id, tenant_timezone=tenant.timezone)
