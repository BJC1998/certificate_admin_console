"""Deterministic demo fixture; sequential reruns add no duplicates or history changes."""
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.database.engine import engine
from app.database.init_db import initialize_database
from app.models import (
    AuditAction, AuditLog, Certificate, CertificateStatus, Course,
    Enrollment, EnrollmentStatus, Learner, Tenant,
)

MODEL_TYPES = (Tenant, Course, Learner, Enrollment, Certificate, AuditLog)
DEMO_TENANTS = ((1, "Sydney", "Australia/Sydney"), (2, "Perth", "Australia/Perth"))


def seed_database(bind: Engine = engine) -> dict[str, int]:
    initialize_database(bind)
    # Maintenance-only session: all owned lookups below explicitly include tenant_id.
    with Session(bind) as session, session.begin():
        for tenant_id, name, timezone in DEMO_TENANTS:
            tenant = session.get(Tenant, tenant_id)
            if tenant is None:
                session.add(Tenant(id=tenant_id, name=name, timezone=timezone))
                session.flush()
            elif (tenant.name, tenant.timezone) != (name, timezone):
                raise ValueError(f"Tenant id {tenant_id} is occupied by non-demo data; refusing to overwrite.")
            courses = []
            for title in ("Workplace Safety", "Data Privacy", "Leadership Essentials"):
                course = session.scalar(select(Course).where(Course.tenant_id == tenant_id, Course.title == title))
                if course is None:
                    course = Course(tenant_id=tenant_id, title=title)
                    session.add(course)
                    session.flush()
                courses.append(course)
            for number in range(1, 31):
                learner_name = f"{name} Learner {number:02d}"
                learner = session.scalar(select(Learner).where(Learner.tenant_id == tenant_id, Learner.name == learner_name))
                if learner is None:
                    learner = Learner(tenant_id=tenant_id, name=learner_name)
                    session.add(learner)
                    session.flush()
                for course_number, course in enumerate(courses):
                    enrollment = session.scalar(select(Enrollment).where(
                        Enrollment.tenant_id == tenant_id, Enrollment.course_id == course.id,
                        Enrollment.learner_id == learner.id))
                    if enrollment is None:
                        enrollment = Enrollment(
                            tenant_id=tenant_id, course_id=course.id, learner_id=learner.id,
                            status=EnrollmentStatus.COMPLETED if number <= 24 else EnrollmentStatus.INCOMPLETE)
                        session.add(enrollment)
                        session.flush()
                    if number > 18 or not enrollment.is_eligible:
                        continue
                    certificate = session.scalar(select(Certificate).where(
                        Certificate.tenant_id == tenant_id, Certificate.course_id == course.id,
                        Certificate.learner_id == learner.id))
                    if certificate is not None:
                        continue  # Never restore revoked certificates or rewrite history.
                    issued_at = datetime(2026, 9, 25, 15, 30, tzinfo=UTC) + timedelta(days=number, hours=course_number)
                    revoked = number % 6 == 0
                    certificate = Certificate(
                        tenant_id=tenant_id, course_id=course.id, learner_id=learner.id,
                        serial_number=f"OCEAN-DEMO-{tenant_id}-{course_number + 1}-{number:03d}",
                        issued_at=issued_at, status=CertificateStatus.REVOKED if revoked else CertificateStatus.VALID)
                    session.add(certificate)
                    session.flush()
                    session.add(AuditLog(
                        tenant_id=tenant_id, certificate_id=certificate.id, course_id=course.id,
                        learner_id=learner.id, action=AuditAction.ISSUED,
                        actor=f"demo-admin-{tenant_id}", created_at=issued_at))
                    if revoked:
                        session.add(AuditLog(
                            tenant_id=tenant_id, certificate_id=certificate.id, course_id=course.id,
                            learner_id=learner.id, action=AuditAction.REVOKED,
                            actor=f"demo-admin-{tenant_id}", created_at=issued_at + timedelta(days=1)))
        session.flush()
        # Explicit maintenance summary across the database; never used by HTTP requests.
        return {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in MODEL_TYPES}


if __name__ == "__main__":
    print(json.dumps(seed_database(), indent=2))
