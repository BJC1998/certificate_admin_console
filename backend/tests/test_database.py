"""Real SQLite integrity and tenant-boundary tests; no production business endpoints."""
import sys
import unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, aliased, selectinload
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.engine import create_sqlite_engine
from app.database.records import get_tenant_record
from app.database.seed import MODEL_TYPES, seed_database
from app.database.session import get_session
from app.database.tenant_session import TenantSession
from app.models import (
    AuditAction, AuditLog, Base, Certificate, CertificateStatus, Course,
    Enrollment, EnrollmentStatus, Learner, Tenant,
)
from app.schemas.data import CourseInput, EnrollmentInput, LearnerInput


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sqlite_engine("sqlite://", poolclass=StaticPool)
        self.counts = seed_database(self.engine)
        with Session(self.engine) as session:
            self.course_a = session.scalar(select(Course.id).where(Course.tenant_id == 1).order_by(Course.id))
            self.course_b = session.scalar(select(Course.id).where(Course.tenant_id == 2).order_by(Course.id))
            self.learner_a = session.scalar(select(Learner.id).where(Learner.tenant_id == 1).order_by(Learner.id))
            self.learner_b = session.scalar(select(Learner.id).where(Learner.tenant_id == 2).order_by(Learner.id))
            self.cert_a = session.scalar(select(Certificate.id).where(Certificate.tenant_id == 1).order_by(Certificate.id))
            self.cert_b = session.scalar(select(Certificate.id).where(Certificate.tenant_id == 2).order_by(Certificate.id))

    def tearDown(self) -> None:
        self.engine.dispose()

    def reject_at_database(self, instance: Base) -> None:
        # Deliberately bypass request guards to test actual database constraints.
        with Session(self.engine) as session:
            session.add(instance)
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()

    def test_seed_is_idempotent_and_preserves_every_row(self) -> None:
        def snapshot() -> list:
            with self.engine.connect() as connection:
                return [connection.execute(select(model.__table__).order_by(model.id)).all() for model in MODEL_TYPES]
        before = snapshot()
        self.assertEqual(seed_database(self.engine), self.counts)
        self.assertEqual(snapshot(), before)
        self.assertEqual(self.counts, {"tenants": 2, "courses": 6, "learners": 60,
                                       "enrollments": 180, "certificates": 108, "audit_logs": 126})

    def test_seed_has_eligible_unissued_and_incomplete_learners(self) -> None:
        with TenantSession(self.engine, tenant_id=1) as session:
            enrollments = session.scalars(select(Enrollment)).all()
            self.assertEqual(sum(item.is_eligible for item in enrollments), 72)
            self.assertEqual(sum(not item.is_eligible for item in enrollments), 18)
            certificates = session.scalars(select(Certificate)).all()
            self.assertEqual(len(certificates), 54)
            self.assertEqual(sum(item.status == CertificateStatus.REVOKED for item in certificates), 9)

    def test_schema_tables_indexes_constraints_and_foreign_keys(self) -> None:
        schema = inspect(self.engine)
        self.assertEqual(set(schema.get_table_names()), set(Base.metadata.tables))
        for model in MODEL_TYPES[1:]:
            table = model.__tablename__
            with self.subTest(table=table):
                self.assertTrue(any("tenant_id" in index["column_names"] for index in schema.get_indexes(table)))
                self.assertTrue(schema.get_foreign_keys(table))
                column = next(column for column in schema.get_columns(table) if column["name"] == "tenant_id")
                self.assertFalse(column["nullable"])
        for table in ("certificates", "enrollments"):
            unique_sets = [constraint["column_names"] for constraint in schema.get_unique_constraints(table)]
            self.assertIn(["tenant_id", "course_id", "learner_id"], unique_sets)
        self.assertIn(["serial_number"], [c["column_names"] for c in schema.get_unique_constraints("certificates")])
        self.assertIn(["tenant_id", "certificate_id", "action"],
                      [c["column_names"] for c in schema.get_unique_constraints("audit_logs")])
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])

    def test_foreign_keys_enabled_on_each_new_connection(self) -> None:
        for _ in range(2):
            engine = create_sqlite_engine("sqlite://")
            with engine.connect() as connection:
                self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1)
            engine.dispose()

    def test_duplicate_certificate_rejected_even_after_revocation(self) -> None:
        for status in (CertificateStatus.VALID, CertificateStatus.REVOKED):
            with Session(self.engine) as session:
                original = session.scalar(select(Certificate).where(Certificate.tenant_id == 1, Certificate.status == status))
                duplicate = Certificate(tenant_id=1, course_id=original.course_id,
                                        learner_id=original.learner_id, serial_number=f"DUP-{status}")
            self.reject_at_database(duplicate)

    def test_duplicate_serial_rejected_across_tenants(self) -> None:
        with Session(self.engine) as session:
            serial = session.get(Certificate, self.cert_a).serial_number
            enrollment = session.scalar(select(Enrollment).where(Enrollment.tenant_id == 2,
                Enrollment.course_id == self.course_b, Enrollment.status == EnrollmentStatus.COMPLETED)
                .order_by(Enrollment.learner_id.desc()))
            duplicate = Certificate(tenant_id=2, course_id=self.course_b, learner_id=enrollment.learner_id, serial_number=serial)
        self.reject_at_database(duplicate)

    def test_duplicate_enrollment_rejected(self) -> None:
        self.reject_at_database(Enrollment(tenant_id=1, course_id=self.course_a, learner_id=self.learner_a))

    def test_cross_tenant_enrollment_rejected_by_database(self) -> None:
        for course_id, learner_id in ((self.course_b, self.learner_a), (self.course_a, self.learner_b)):
            self.reject_at_database(Enrollment(tenant_id=1, course_id=course_id, learner_id=learner_id))

    def test_cross_tenant_certificate_rejected_by_database(self) -> None:
        for course_id, learner_id in ((self.course_b, self.learner_a), (self.course_a, self.learner_b),
                                     (self.course_b, self.learner_b)):
            self.reject_at_database(Certificate(tenant_id=1, course_id=course_id,
                                                learner_id=learner_id, serial_number="CROSS-TENANT"))

    def test_certificate_requires_matching_enrollment(self) -> None:
        with Session(self.engine) as session, session.begin():
            learner = Learner(tenant_id=1, name="No enrollment")
            session.add(learner)
            session.flush()
            learner_id = learner.id
        self.reject_at_database(Certificate(tenant_id=1, course_id=self.course_a,
                                            learner_id=learner_id, serial_number="NO-ENROLLMENT"))

    def test_audit_must_match_certificate_tenant_course_and_learner(self) -> None:
        self.reject_at_database(AuditLog(tenant_id=1, certificate_id=self.cert_b,
            course_id=self.course_b, learner_id=self.learner_b, action=AuditAction.ISSUED, actor="tester"))
        # Same tenant, but mismatched course/learner, must also fail (use a different action).
        self.reject_at_database(AuditLog(tenant_id=1, certificate_id=self.cert_a,
            course_id=self.course_a, learner_id=self.learner_a + 1, action=AuditAction.REVOKED, actor="tester"))

    def test_duplicate_issuance_audit_rejected(self) -> None:
        self.reject_at_database(AuditLog(tenant_id=1, certificate_id=self.cert_a, course_id=self.course_a,
                                        learner_id=self.learner_a, action=AuditAction.ISSUED, actor="retry"))

    def test_owned_record_requires_existing_tenant(self) -> None:
        self.reject_at_database(Course(tenant_id=999, title="Missing tenant"))
        self.reject_at_database(Learner(tenant_id=999, name="Missing tenant"))

    def test_certificate_and_audit_transaction_roll_back_together(self) -> None:
        with Session(self.engine) as session:
            enrollment = session.scalar(select(Enrollment).where(Enrollment.tenant_id == 1,
                Enrollment.course_id == self.course_a, Enrollment.status == EnrollmentStatus.COMPLETED)
                .order_by(Enrollment.learner_id.desc()))
            learner_id = enrollment.learner_id
        with Session(self.engine) as session:
            with self.assertRaises(IntegrityError), session.begin():
                certificate = Certificate(tenant_id=1, course_id=self.course_a, learner_id=learner_id, serial_number="ROLLBACK")
                session.add(certificate)
                session.flush()
                session.add(AuditLog(tenant_id=1, certificate_id=certificate.id, course_id=self.course_b,
                    learner_id=learner_id, action=AuditAction.ISSUED, actor="tester"))
            self.assertIsNone(session.scalar(select(Certificate).where(Certificate.tenant_id == 1, Certificate.serial_number == "ROLLBACK")))

    def test_all_owned_queries_are_scoped_even_without_manual_filter(self) -> None:
        for tenant_id in (1, 2, 1):
            with TenantSession(self.engine, tenant_id=tenant_id) as session:
                for model in MODEL_TYPES[1:]:
                    rows = session.scalars(select(model)).all()
                    self.assertTrue(rows)
                    self.assertTrue(all(row.tenant_id == tenant_id for row in rows))
                self.assertEqual([tenant.id for tenant in session.scalars(select(Tenant))], [tenant_id])
                self.assertEqual(session.scalar(select(func.count()).select_from(Certificate)), 54)

    def test_aliases_projections_and_relationship_loads_are_scoped(self) -> None:
        with TenantSession(self.engine, tenant_id=1) as session:
            other = aliased(Certificate)
            self.assertEqual(len(session.scalars(select(other)).all()), 54)
            self.assertEqual(set(session.scalars(select(Certificate.tenant_id))), {1})
            rows = session.scalars(select(Certificate).options(selectinload(Certificate.course))).all()
            self.assertTrue(all(row.course.tenant_id == 1 for row in rows))

    def test_inaccessible_lookup_returns_404_for_each_owned_type(self) -> None:
        with Session(self.engine) as maintenance:
            foreign_ids = {model: maintenance.scalar(select(model.id).where(model.tenant_id == 2)) for model in MODEL_TYPES[1:]}
        with TenantSession(self.engine, tenant_id=1) as session:
            for model, foreign_id in foreign_ids.items():
                with self.subTest(model=model.__name__):
                    self.assertIsNone(session.get(model, foreign_id))
                    with self.assertRaises(HTTPException) as error:
                        get_tenant_record(session, model, foreign_id)
                    self.assertEqual(error.exception.status_code, 404)

    def test_cross_tenant_attach_or_write_rejected_without_modifying_foreign_data(self) -> None:
        with TenantSession(self.engine, tenant_id=1) as session:
            with self.assertRaises(HTTPException) as error:
                session.add(Course(tenant_id=2, title="Injected"))
            self.assertEqual(error.exception.status_code, 404)
        with TenantSession(self.engine, tenant_id=1) as session:
            session.add(Enrollment(course_id=self.course_b, learner_id=self.learner_a))
            with self.assertRaises(HTTPException) as error:
                session.commit()
            self.assertEqual(error.exception.status_code, 404)
            session.rollback()
        with TenantSession(self.engine, tenant_id=2) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Course)), 3)

    def test_owner_assigned_from_session_and_is_immutable(self) -> None:
        with TenantSession(self.engine, tenant_id=1) as session:
            course = Course(title="Own new course")
            session.add(course)
            session.commit()
            self.assertEqual(course.tenant_id, 1)
            course.tenant_id = 2
            with self.assertRaises(HTTPException):
                session.commit()
            session.rollback()

    def test_raw_sql_core_queries_bulk_dml_and_mapping_apis_rejected(self) -> None:
        with TenantSession(self.engine, tenant_id=1) as session:
            statements = (text("SELECT * FROM certificates"), select(Certificate.__table__),
                          update(Course).values(title="Bad"), delete(Course),
                          select(Certificate).from_statement(text("SELECT * FROM certificates")))
            for statement in statements:
                with self.assertRaises(ValueError):
                    session.execute(statement)
            with self.assertRaises(ValueError):
                session.bulk_insert_mappings(Course, [{"tenant_id": 2, "title": "Bad"}])

    def test_request_body_tenant_id_is_forbidden(self) -> None:
        inputs = ((CourseInput, {"title": "Test"}), (LearnerInput, {"name": "Test"}),
                  (EnrollmentInput, {"course_id": 1, "learner_id": 1}))
        for schema, data in inputs:
            with self.assertRaises(ValidationError):
                schema.model_validate({**data, "tenant_id": 2})

    def test_utc_round_trip_and_naive_timestamps_rejected(self) -> None:
        local = datetime(2026, 10, 4, 3, 30, tzinfo=timezone(timedelta(hours=11)))
        with Session(self.engine) as session, session.begin():
            certificate = session.get(Certificate, self.cert_a)
            certificate.issued_at = local
        with Session(self.engine) as session:
            self.assertEqual(session.get(Certificate, self.cert_a).issued_at, local.astimezone(UTC))
            self.assertIs(session.get(Certificate, self.cert_a).issued_at.tzinfo, UTC)
            audit = session.scalar(select(AuditLog).where(AuditLog.tenant_id == 1))
            self.assertIs(audit.created_at.tzinfo, UTC)
            session.get(Certificate, self.cert_a).issued_at = datetime(2026, 10, 4)
            with self.assertRaises(StatementError):
                session.commit()
            session.rollback()

    def test_invalid_timezone_and_status_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Tenant(name="Bad", timezone="UTC+10")
        with self.engine.begin() as connection:
            with self.assertRaises(IntegrityError):
                connection.exec_driver_sql("UPDATE enrollments SET status='invalid' WHERE tenant_id=1")
            with self.assertRaises(IntegrityError):
                connection.exec_driver_sql("UPDATE certificates SET status='deleted' WHERE tenant_id=1")

    def test_certificate_history_and_audit_are_preserved(self) -> None:
        with TenantSession(self.engine, tenant_id=1) as session:
            certificate = session.get(Certificate, self.cert_a)
            session.delete(certificate)
            with self.assertRaises(ValueError):
                session.flush()
            session.rollback()
            certificate = session.get(Certificate, self.cert_a)
            certificate.serial_number = "REPLACED"
            with self.assertRaises(ValueError):
                session.flush()
            session.rollback()
            audit = session.scalar(select(AuditLog))
            audit.actor = "rewritten"
            with self.assertRaises(ValueError):
                session.flush()
            session.rollback()
            audit = session.scalar(select(AuditLog))
            session.delete(audit)
            with self.assertRaises(ValueError):
                session.flush()
            session.rollback()

    def test_http_dependency_validates_demo_context_and_404(self) -> None:
        # Test-only routes exercise the real dependency. Nothing added to production app.
        app = FastAPI()

        @app.get("/probe/{record_id}")
        def probe(record_id: int, session: Annotated[TenantSession, Depends(get_session)]):
            course = get_tenant_record(session, Course, record_id)
            return {"id": course.id, "tenant_id": course.tenant_id}

        @app.put("/probe/{record_id}")
        def mutate_probe(record_id: int, body: CourseInput,
                         session: Annotated[TenantSession, Depends(get_session)]):
            course = get_tenant_record(session, Course, record_id)
            course.title = body.title
            session.commit()
            return {"tenant_id": course.tenant_id}

        with patch("app.core.tenant.engine", self.engine), patch("app.database.session.SessionLocal",
                side_effect=lambda **kwargs: TenantSession(self.engine, **kwargs)):
            with TestClient(app) as client:
                self.assertEqual(client.get(f"/probe/{self.course_a}", headers={"X-Tenant-ID": "1"}).status_code, 200)
                response = client.get(f"/probe/{self.course_b}", headers={"X-Tenant-ID": "1"})
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "Resource not found"})
                self.assertEqual(client.get(f"/probe/{self.course_a}", headers={"X-Tenant-ID": "999"}).status_code, 404)
                self.assertEqual(client.get(f"/probe/{self.course_a}").status_code, 422)
                self.assertEqual(client.get(f"/probe/{self.course_a}", headers={"X-Tenant-ID": "0"}).status_code, 422)
                self.assertEqual(client.put(f"/probe/{self.course_b}", headers={"X-Tenant-ID": "1"},
                                            json={"title": "Cross-tenant overwrite"}).status_code, 404)
                self.assertEqual(client.put(f"/probe/{self.course_a}", headers={"X-Tenant-ID": "1"},
                                            json={"title": "Injected", "tenant_id": 2}).status_code, 422)
                self.assertEqual(client.put(f"/probe/{self.course_a}", headers={"X-Tenant-ID": "1"},
                                            json={"title": "Own tenant update"}).status_code, 200)
        with TenantSession(self.engine, tenant_id=2) as session:
            self.assertEqual(session.get(Course, self.course_b).title, "Workplace Safety")


if __name__ == "__main__":
    unittest.main()
