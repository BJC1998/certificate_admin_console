"""Fixed-tenant ORM boundary. Request sessions reject raw SQL and bulk DML."""
from fastapi import HTTPException
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.models import AuditLog, Certificate, Course, Enrollment, Learner, Tenant, TenantOwned


class TenantSession(Session):
    def __init__(self, *args: object, tenant_id: int, **kwargs: object) -> None:
        if tenant_id <= 0:
            raise ValueError("A positive selected tenant id is required.")
        self._tenant_id = tenant_id
        super().__init__(*args, **kwargs)

    @property
    def tenant_id(self) -> int:
        return self._tenant_id

    def bulk_save_objects(self, *args: object, **kwargs: object) -> None:
        raise ValueError("Use tenant-scoped unit-of-work writes, not bulk mapping APIs.")

    bulk_insert_mappings = bulk_save_objects
    bulk_update_mappings = bulk_save_objects


@event.listens_for(TenantSession, "do_orm_execute")
def scope_queries(state: ORMExecuteState) -> None:
    if not state.is_select or not state.is_orm_statement or state.is_from_statement:
        raise ValueError("Request sessions only accept ORM SELECT; use add/flush for writes.")
    tenant_id = state.session.tenant_id
    state.statement = state.statement.options(
        with_loader_criteria(TenantOwned, lambda model: model.tenant_id == tenant_id, include_aliases=True),
        with_loader_criteria(Tenant, lambda model: model.id == tenant_id, include_aliases=True),
    )


def enforce_owner(session: TenantSession, instance: object) -> None:
    if isinstance(instance, TenantOwned):
        if instance.tenant_id is None and inspect(instance).transient:
            instance.tenant_id = session.tenant_id
        if instance.tenant_id != session.tenant_id:
            raise HTTPException(status_code=404, detail="Resource not found")
    elif isinstance(instance, Tenant):
        if inspect(instance).transient or instance.id != session.tenant_id:
            raise HTTPException(status_code=404, detail="Resource not found")
    else:
        raise ValueError("Unrecognized model in request session.")


@event.listens_for(TenantSession, "before_attach")
def validate_attachment(session: TenantSession, instance: object) -> None:
    enforce_owner(session, instance)


@event.listens_for(TenantSession, "before_flush")
def validate_writes(session: TenantSession, _flush_context: object, _instances: object) -> None:
    for instance in session.new | session.dirty | session.deleted:
        enforce_owner(session, instance)
        if instance not in session.deleted:
            # Check references through the selected tenant before a write reaches SQLite.
            # The composite foreign keys remain the final race-safe authority.
            for field, model in (("course_id", Course), ("learner_id", Learner), ("certificate_id", Certificate)):
                if hasattr(instance, field):
                    related = session.get(model, getattr(instance, field))
                    if related is None:
                        raise HTTPException(status_code=404, detail="Resource not found")
                    if isinstance(instance, AuditLog) and model is Certificate:
                        if (related.course_id, related.learner_id) != (instance.course_id, instance.learner_id):
                            raise HTTPException(status_code=404, detail="Resource not found")
            if isinstance(instance, Certificate):
                enrollment = session.scalar(select(Enrollment).where(
                    Enrollment.course_id == instance.course_id, Enrollment.learner_id == instance.learner_id))
                if enrollment is None:
                    raise HTTPException(status_code=404, detail="Resource not found")
        state = inspect(instance)
        if state.persistent and isinstance(instance, TenantOwned):
            if state.attrs.tenant_id.history.has_changes():
                raise ValueError("Tenant ownership is immutable.")
        if isinstance(instance, AuditLog) and state.persistent:
            raise ValueError("Audit logs are append-only.")
        if isinstance(instance, Certificate) and state.persistent:
            if instance in session.deleted:
                raise ValueError("Certificates must be preserved; use revocation.")
            for field in ("id", "tenant_id", "course_id", "learner_id", "serial_number", "issued_at"):
                if state.attrs[field].history.has_changes():
                    raise ValueError("Issued certificate identity is immutable.")
