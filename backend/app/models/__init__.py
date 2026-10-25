"""Import all models to register the explicit schema."""
from app.models.base import Base, TenantOwned
from app.models.domain import (
    AuditAction, AuditLog, Certificate, CertificateStatus, Course,
    Enrollment, EnrollmentStatus, Learner, Tenant,
)

__all__ = ["Base", "TenantOwned", "Tenant", "Course", "Learner", "Enrollment",
           "Certificate", "AuditLog", "EnrollmentStatus", "CertificateStatus", "AuditAction"]
