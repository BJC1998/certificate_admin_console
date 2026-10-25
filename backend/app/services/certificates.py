"""Read-only server-side certificate search, pagination and allowlisted sorting."""
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.database.tenant_session import TenantSession
from app.schemas.certificates import CertificatePage, CertificateQuery, CertificateRecord
from app.services.certificate_queries import certificate_ordering, certificate_statement, selected_tenant


def list_certificates(session: TenantSession, query: CertificateQuery) -> CertificatePage:
    tenant_id = session.tenant_id
    tenant = selected_tenant(session)
    base = certificate_statement(tenant_id, query)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(base.order_by(*certificate_ordering(query, tenant.timezone))
        .offset((query.page - 1) * query.page_size).limit(query.page_size)).all()
    timezone = ZoneInfo(tenant.timezone)
    records = [CertificateRecord(
        id=row.id, tenant_id=tenant_id, learner_name=row.learner_name, course_title=row.course_title,
        serial_number=row.serial_number, issued_at=row.issued_at.astimezone(timezone), status=row.status,
    ) for row in rows]
    return CertificatePage(records=records, total=total, page=query.page, page_size=query.page_size,
                           total_pages=(total + query.page_size - 1) // query.page_size,
                           tenant_id=tenant_id, tenant_timezone=tenant.timezone)
