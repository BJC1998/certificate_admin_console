"""Tenant-scoped details and atomic, retry-safe revocation."""
import sqlite3
import time
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.database.records import get_tenant_record
from app.database.tenant_session import TenantSession
from app.models import AuditAction, AuditLog, Certificate, CertificateStatus, Course, Learner, Tenant
from app.schemas.certificates import CertificateDetail, RevokeResponse


def certificate_detail(session: TenantSession, certificate_id: int) -> CertificateDetail:
    tenant_id = session.tenant_id
    row = session.execute(select(Certificate, Learner.name, Course.title, Tenant.name, Tenant.timezone)
        .join(Learner, and_(Learner.id == Certificate.learner_id, Learner.tenant_id == tenant_id))
        .join(Course, and_(Course.id == Certificate.course_id, Course.tenant_id == tenant_id))
        .join(Tenant, Tenant.id == tenant_id)
        .where(Certificate.tenant_id == tenant_id, Certificate.id == certificate_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    certificate, learner_name, course_title, tenant_name, timezone = row
    return CertificateDetail(id=certificate.id, tenant_id=tenant_id, learner_id=certificate.learner_id,
        learner_name=learner_name, course_id=certificate.course_id, course_title=course_title,
        serial_number=certificate.serial_number, issued_at=certificate.issued_at.astimezone(ZoneInfo(timezone)),
        status=certificate.status, tenant_name=tenant_name, tenant_timezone=timezone)


def revoke_certificate(session: TenantSession, certificate_id: int) -> RevokeResponse:
    for attempt in range(4):
        try:
            with session.begin():
                certificate = get_tenant_record(session, Certificate, certificate_id)
                changed = certificate.status == CertificateStatus.VALID
                if changed:
                    certificate.status = CertificateStatus.REVOKED
                    session.add(AuditLog(tenant_id=session.tenant_id, certificate_id=certificate.id,
                        course_id=certificate.course_id, learner_id=certificate.learner_id,
                        action=AuditAction.REVOKED, actor=f"demo-admin-{session.tenant_id}"))
                    session.flush()  # State change and audit both roll back on any failure.
                result = RevokeResponse(certificate=certificate_detail(session, certificate_id), changed=changed)
            return result  # Successful commit precedes the response.
        except IntegrityError:
            # A concurrent winner can have changed state and inserted the unique audit action.
            try:
                with session.begin():
                    certificate = get_tenant_record(session, Certificate, certificate_id)
                    audit = session.scalar(select(AuditLog.id).where(AuditLog.tenant_id == session.tenant_id,
                        AuditLog.certificate_id == certificate_id, AuditLog.action == AuditAction.REVOKED))
                    if certificate.status == CertificateStatus.REVOKED and audit is not None:
                        return RevokeResponse(certificate=certificate_detail(session, certificate_id), changed=False)
            except SQLAlchemyError:
                pass
            raise HTTPException(status_code=503, detail="Revocation could not be confirmed. Reload or retry safely.",
                                headers={"Retry-After": "1"}) from None
        except OperationalError as error:
            code = getattr(error.orig, "sqlite_errorcode", 0) & 0xFF
            if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) and attempt < 3:
                time.sleep(0.025 * (2 ** attempt))
                continue
            raise HTTPException(status_code=503, detail="Database unavailable. Reload or retry revocation safely.",
                                headers={"Retry-After": "1"}) from None
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="Revocation could not be confirmed. Reload or retry safely.",
                                headers={"Retry-After": "1"}) from None
    raise HTTPException(status_code=503, detail="Reload or retry revocation safely.")
