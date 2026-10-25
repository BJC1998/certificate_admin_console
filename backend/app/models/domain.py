"""Tenant-safe schema. Navigation relationships are read-only; write explicit FK fields."""
from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import CheckConstraint, Enum, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import Base, TenantOwned, UTCDateTime, utc_now


class EnrollmentStatus(StrEnum):
    INCOMPLETE = "incomplete"
    COMPLETED = "completed"


class CertificateStatus(StrEnum):
    VALID = "valid"
    REVOKED = "revoked"


class AuditAction(StrEnum):
    ISSUED = "issued"
    REVOKED = "revoked"


def status_column(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(enum_type, name=name, native_enum=False, create_constraint=True,
                validate_strings=True, values_callable=lambda values: [item.value for item in values])


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_tenants_name"),
        CheckConstraint("length(trim(timezone)) > 0", name="ck_tenants_timezone"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(100))
    courses: Mapped[list["Course"]] = relationship(viewonly=True, lazy="raise")
    learners: Mapped[list["Learner"]] = relationship(viewonly=True, lazy="raise")

    @validates("timezone")
    def validate_timezone(self, key: str, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValueError("Tenant timezone must be a valid IANA timezone name.") from exc
        return value


class Course(TenantOwned, Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_courses_tenant_id_id"),
        CheckConstraint("length(trim(title)) > 0", name="ck_courses_title"),
        Index("ix_courses_tenant_title", "tenant_id", "title"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    tenant: Mapped[Tenant] = relationship(viewonly=True, lazy="raise")
    enrollments: Mapped[list["Enrollment"]] = relationship(viewonly=True, lazy="raise")


class Learner(TenantOwned, Base):
    __tablename__ = "learners"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_learners_tenant_id_id"),
        CheckConstraint("length(trim(name)) > 0", name="ck_learners_name"),
        Index("ix_learners_tenant_name", "tenant_id", "name"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tenant: Mapped[Tenant] = relationship(viewonly=True, lazy="raise")
    enrollments: Mapped[list["Enrollment"]] = relationship(viewonly=True, lazy="raise")


class Enrollment(TenantOwned, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "course_id", "learner_id", name="uq_enrollments_tenant_course_learner"),
        ForeignKeyConstraint(["tenant_id", "course_id"], ["courses.tenant_id", "courses.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "learner_id"], ["learners.tenant_id", "learners.id"], ondelete="RESTRICT"),
        Index("ix_enrollments_tenant_course_status", "tenant_id", "course_id", "status"),
        Index("ix_enrollments_tenant_learner", "tenant_id", "learner_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(nullable=False)
    learner_id: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[EnrollmentStatus] = mapped_column(
        status_column(EnrollmentStatus, "ck_enrollments_status"), default=EnrollmentStatus.INCOMPLETE)
    course: Mapped[Course] = relationship(viewonly=True, lazy="raise")
    learner: Mapped[Learner] = relationship(viewonly=True, lazy="raise")

    @property
    def is_eligible(self) -> bool:
        return self.status == EnrollmentStatus.COMPLETED


class Certificate(TenantOwned, Base):
    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "course_id", "learner_id", name="uq_certificates_tenant_course_learner"),
        UniqueConstraint("serial_number", name="uq_certificates_serial_number"),
        UniqueConstraint("tenant_id", "id", "course_id", "learner_id", name="uq_certificates_audit_reference"),
        ForeignKeyConstraint(["tenant_id", "course_id"], ["courses.tenant_id", "courses.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "learner_id"], ["learners.tenant_id", "learners.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "course_id", "learner_id"],
                             ["enrollments.tenant_id", "enrollments.course_id", "enrollments.learner_id"], ondelete="RESTRICT"),
        CheckConstraint("length(trim(serial_number)) > 0", name="ck_certificates_serial"),
        Index("ix_certificates_tenant_issued_id", "tenant_id", "issued_at", "id"),
        Index("ix_certificates_tenant_status", "tenant_id", "status"),
        Index("ix_certificates_tenant_learner", "tenant_id", "learner_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(nullable=False)
    learner_id: Mapped[int] = mapped_column(nullable=False)
    serial_number: Mapped[str] = mapped_column(String(100))
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    status: Mapped[CertificateStatus] = mapped_column(
        status_column(CertificateStatus, "ck_certificates_status"), default=CertificateStatus.VALID)
    course: Mapped[Course] = relationship(viewonly=True, lazy="raise")
    learner: Mapped[Learner] = relationship(viewonly=True, lazy="raise")
    enrollment: Mapped[Enrollment] = relationship(viewonly=True, lazy="raise")
    audit_logs: Mapped[list["AuditLog"]] = relationship(viewonly=True, lazy="raise")


class AuditLog(TenantOwned, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "certificate_id", "course_id", "learner_id"],
                             ["certificates.tenant_id", "certificates.id", "certificates.course_id", "certificates.learner_id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "certificate_id", "action", name="uq_audit_logs_certificate_action"),
        CheckConstraint("length(trim(actor)) > 0", name="ck_audit_logs_actor"),
        Index("ix_audit_logs_tenant_created_id", "tenant_id", "created_at", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    certificate_id: Mapped[int] = mapped_column(nullable=False)
    course_id: Mapped[int] = mapped_column(nullable=False)
    learner_id: Mapped[int] = mapped_column(nullable=False)
    action: Mapped[AuditAction] = mapped_column(status_column(AuditAction, "ck_audit_logs_action"))
    actor: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    certificate: Mapped[Certificate] = relationship(viewonly=True, lazy="raise")
