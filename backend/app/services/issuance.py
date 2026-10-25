"""Synchronous, retry-safe issuance. Each learner has a separate durable transaction."""
import logging
import sqlite3
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.database.records import get_tenant_record
from app.database.tenant_session import TenantSession
from app.models import AuditAction, AuditLog, Certificate, CertificateStatus, Course, Enrollment, Learner
from app.models.base import utc_now
from app.schemas.issuance import CourseOption, IssueSummary, LearnerOutcome

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 4


def list_courses(session: TenantSession) -> list[CourseOption]:
    rows = session.scalars(select(Course).where(Course.tenant_id == session.tenant_id).order_by(Course.title, Course.id))
    return [CourseOption(id=row.id, tenant_id=row.tenant_id, title=row.title) for row in rows]


def generate_serial() -> str:
    return f"OCEAN-{uuid4().hex.upper()}"


def existing_certificate(session: TenantSession, course_id: int, learner_id: int) -> Certificate | None:
    return session.scalar(select(Certificate).where(
        Certificate.tenant_id == session.tenant_id,
        Certificate.course_id == course_id, Certificate.learner_id == learner_id))


def skipped_existing(certificate: Certificate, learner_name: str) -> LearnerOutcome:
    return LearnerOutcome(learner_id=certificate.learner_id, learner_name=learner_name, outcome="skipped",
        reason="previously_revoked" if certificate.status == CertificateStatus.REVOKED else "already_issued",
        certificate_id=certificate.id, serial_number=certificate.serial_number)


def issue_one(session: TenantSession, course_id: int, learner_id: int, learner_name: str) -> LearnerOutcome:
    def failed(reason: str) -> LearnerOutcome:
        return LearnerOutcome(learner_id=learner_id, learner_name=learner_name, outcome="failed", reason=reason)

    for attempt in range(MAX_ATTEMPTS):
        try:
            with session.begin():
                enrollment = session.scalar(select(Enrollment).where(
                    Enrollment.tenant_id == session.tenant_id,
                    Enrollment.course_id == course_id, Enrollment.learner_id == learner_id))
                if enrollment is None:
                    return failed("enrollment_no_longer_available")
                existing = existing_certificate(session, course_id, learner_id)
                if existing is not None:
                    return skipped_existing(existing, learner_name)
                if not enrollment.is_eligible:
                    return LearnerOutcome(learner_id=learner_id, learner_name=learner_name,
                                          outcome="skipped", reason="enrollment_incomplete")
                issued_at = utc_now()
                certificate = Certificate(tenant_id=session.tenant_id, course_id=course_id,
                    learner_id=learner_id, serial_number=generate_serial(), issued_at=issued_at,
                    status=CertificateStatus.VALID)
                session.add(certificate)
                session.flush()  # The unique constraint arbitrates races; this is not an upsert.
                session.add(AuditLog(tenant_id=session.tenant_id, certificate_id=certificate.id,
                    course_id=course_id, learner_id=learner_id, action=AuditAction.ISSUED,
                    actor=f"demo-admin-{session.tenant_id}", created_at=issued_at))
                session.flush()
                result = LearnerOutcome(learner_id=learner_id, learner_name=learner_name, outcome="issued",
                    reason="certificate_and_audit_committed", certificate_id=certificate.id,
                    serial_number=certificate.serial_number)
            # Only report issued AFTER the transaction context successfully commits.
            return result
        except IntegrityError:
            # The failed learner transaction has already rolled back, including any certificate insert.
            try:
                with session.begin():
                    winner = existing_certificate(session, course_id, learner_id)
                    if winner is not None:
                        return skipped_existing(winner, learner_name)
            except SQLAlchemyError:
                return failed("database_error_retry_safe")
            logger.warning("Issuance integrity failure for tenant %s, learner %s", session.tenant_id, learner_id)
            return failed("database_integrity_error_retry_safe")
        except OperationalError as error:
            code = getattr(error.orig, "sqlite_errorcode", 0) & 0xFF
            if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                return failed("database_error_retry_safe")
            if attempt + 1 == MAX_ATTEMPTS:
                return failed("database_busy_retry_safe")
            time.sleep(0.025 * (2 ** attempt))
        except SQLAlchemyError:
            return failed("database_error_retry_safe")
        except HTTPException:
            # A referenced row disappeared/changed since the batch snapshot. Never expose foreign data.
            return failed("enrollment_no_longer_available")
    return failed("database_busy_retry_safe")


def bulk_issue(session: TenantSession, course_id: int) -> IssueSummary:
    get_tenant_record(session, Course, course_id)
    learners = session.execute(select(Enrollment.learner_id, Learner.name)
        .join(Learner, and_(Learner.id == Enrollment.learner_id, Learner.tenant_id == session.tenant_id))
        .where(Enrollment.tenant_id == session.tenant_id, Enrollment.course_id == course_id)
        .order_by(Enrollment.learner_id)).all()
    # Materialized scalar snapshot only; end the read transaction before per-learner writes.
    session.rollback()
    results = [issue_one(session, course_id, learner_id, name) for learner_id, name in learners]
    return IssueSummary(tenant_id=session.tenant_id, course_id=course_id, total=len(results),
        issued=sum(row.outcome == "issued" for row in results),
        skipped=sum(row.outcome == "skipped" for row in results),
        failed=sum(row.outcome == "failed" for row in results), results=results)
