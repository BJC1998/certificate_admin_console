"""Real file-backed SQLite, separate connections and concurrent HTTP requests."""
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.engine import create_sqlite_engine
from app.database.seed import seed_database
from app.database.tenant_session import TenantSession
from app.main import app
from app.models import AuditAction, AuditLog, Certificate, CertificateStatus, Course, Learner
from app.services import issuance


class BulkIssuanceTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_root = Path(__file__).resolve().parents[2] / "tmp"
        temp_root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temp_root)
        self.engine = create_sqlite_engine(f"sqlite:///{Path(self.directory.name).as_posix()}/bulk.db")
        seed_database(self.engine)
        self.patches = [patch("app.core.tenant.engine", self.engine),
            patch("app.database.session.SessionLocal", side_effect=lambda **kwargs: TenantSession(self.engine, **kwargs))]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)
        with Session(self.engine) as session:
            self.course_a = session.scalar(select(Course.id).where(Course.tenant_id == 1).order_by(Course.id))
            self.course_b = session.scalar(select(Course.id).where(Course.tenant_id == 2).order_by(Course.id))
            self.first_new = session.scalar(select(Learner.id).where(Learner.tenant_id == 1, Learner.name == "Sydney Learner 19"))
        self.url = f"/api/tenants/1/courses/{self.course_a}/issue"

    def tearDown(self) -> None:
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()
        self.directory.cleanup()

    def counts(self) -> tuple[int, int]:
        with Session(self.engine) as session:
            certificates = session.scalar(select(func.count()).select_from(Certificate).where(
                Certificate.tenant_id == 1, Certificate.course_id == self.course_a))
            audits = session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.tenant_id == 1, AuditLog.course_id == self.course_a, AuditLog.action == AuditAction.ISSUED))
            return certificates, audits

    def post(self) -> dict:
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_first_request_repeat_and_exactly_one_issuance_audit(self) -> None:
        self.assertEqual(self.counts(), (18, 18))
        first = self.post()
        self.assertEqual((first["issued"], first["skipped"], first["failed"], first["total"]), (6, 24, 0, 30))
        self.assertEqual(self.counts(), (24, 24))
        second = self.post()
        self.assertEqual((second["issued"], second["skipped"], second["failed"]), (0, 30, 0))
        self.assertEqual(self.counts(), (24, 24))
        with Session(self.engine) as session:
            groups = session.execute(select(AuditLog.certificate_id, func.count()).where(
                AuditLog.tenant_id == 1, AuditLog.course_id == self.course_a, AuditLog.action == AuditAction.ISSUED)
                .group_by(AuditLog.certificate_id)).all()
            self.assertTrue(all(count == 1 for _, count in groups))
        print("EVIDENCE first/repeat: issued 6 then 0; certificates=24, issuance audits=24")

    def test_existing_revoked_and_incomplete_are_skipped(self) -> None:
        with Session(self.engine) as session:
            revoked_before = [(row.id, row.serial_number, row.issued_at) for row in session.scalars(
                select(Certificate).where(Certificate.tenant_id == 1, Certificate.course_id == self.course_a,
                                          Certificate.status == CertificateStatus.REVOKED))]
        result = self.post()
        self.assertEqual(sum(row["reason"] == "already_issued" for row in result["results"]), 15)
        self.assertEqual(sum(row["reason"] == "previously_revoked" for row in result["results"]), 3)
        self.assertEqual(sum(row["reason"] == "enrollment_incomplete" for row in result["results"]), 6)
        with Session(self.engine) as session:
            revoked_after = [(row.id, row.serial_number, row.issued_at) for row in session.scalars(
                select(Certificate).where(Certificate.tenant_id == 1, Certificate.course_id == self.course_a,
                                          Certificate.status == CertificateStatus.REVOKED))]
            self.assertEqual(revoked_after, revoked_before)

    def test_two_concurrent_http_requests_with_forced_insert_race(self) -> None:
        barrier = threading.Barrier(2)
        seen = set()
        lock = threading.Lock()
        original = issuance.existing_certificate
        conflicts = []

        def synchronized_lookup(session, course_id, learner_id):
            certificate = original(session, course_id, learner_id)
            wait = False
            if learner_id == self.first_new and certificate is None:
                with lock:
                    key = threading.get_ident()
                    if key not in seen:
                        seen.add(key)
                        wait = True
            if wait:
                barrier.wait(timeout=15)  # Both real requests see no certificate before either inserts.
            return certificate

        @event.listens_for(self.engine, "handle_error")
        def observe_conflicts(context):
            conflicts.append(getattr(context.original_exception, "sqlite_errorcode", None))

        def request():
            with TestClient(app) as client:
                response = client.post(self.url)
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()

        with patch.object(issuance, "existing_certificate", side_effect=synchronized_lookup):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(request) for _ in range(2)]
                results = [future.result(timeout=30) for future in futures]
        self.assertEqual(sum(row["issued"] for row in results), 6)
        self.assertEqual(sum(row["failed"] for row in results), 0)
        self.assertEqual(self.counts(), (24, 24))
        self.assertIn(sqlite3.SQLITE_CONSTRAINT_UNIQUE, conflicts)
        print(f"EVIDENCE concurrent HTTP: issued={[row['issued'] for row in results]}, unique_conflict_codes={conflicts}; certificates/audits={self.counts()}")

    def test_response_lost_after_commit_then_retry(self) -> None:
        async def lose_response(scope, receive, send):
            if scope["type"] == "http" and scope["method"] == "POST":
                async def discard(message):
                    pass
                await app(scope, receive, discard)  # Endpoint finishes and all commits complete.
                raise ConnectionResetError("Simulated response loss after database commits")
            await app(scope, receive, send)

        with TestClient(lose_response) as client:
            with self.assertRaises(ConnectionResetError):
                client.post(self.url)
        self.assertEqual(self.counts(), (24, 24))
        retry = self.post()
        self.assertEqual((retry["issued"], retry["skipped"], retry["failed"]), (0, 30, 0))
        self.assertEqual(self.counts(), (24, 24))
        print("EVIDENCE lost response after commit: retry issued=0; certificates=24, issuance audits=24")

    def test_audit_failure_rolls_back_only_its_certificate_then_retry_recovers(self) -> None:
        def reject_audit(mapper, connection, target):
            if target.learner_id == self.first_new:
                raise IntegrityError("Injected audit failure", {}, Exception("test failure"))
        event.listen(AuditLog, "before_insert", reject_audit)
        try:
            result = self.post()
        finally:
            event.remove(AuditLog, "before_insert", reject_audit)
        self.assertEqual((result["issued"], result["failed"]), (5, 1))
        self.assertEqual(self.counts(), (23, 23))
        with Session(self.engine) as session:
            self.assertIsNone(session.scalar(select(Certificate).where(Certificate.tenant_id == 1,
                Certificate.course_id == self.course_a, Certificate.learner_id == self.first_new)))
        retry = self.post()
        self.assertEqual((retry["issued"], retry["skipped"], retry["failed"]), (1, 29, 0))
        self.assertEqual(self.counts(), (24, 24))
        print("EVIDENCE atomic failure: 5 learners committed, 1 certificate+audit rolled back; retry recovered 1")

    def test_serial_constraint_failure_is_not_misreported_as_already_issued(self) -> None:
        with Session(self.engine) as session:
            serial = session.scalar(select(Certificate.serial_number).where(Certificate.tenant_id == 1))
        generate = issuance.generate_serial
        values = iter([serial] + [generate() for _ in range(5)])
        with patch.object(issuance, "generate_serial", side_effect=lambda: next(values)):
            result = self.post()
        self.assertEqual((result["issued"], result["skipped"], result["failed"]), (5, 24, 1))
        self.assertEqual(self.counts(), (23, 23))

    def test_real_sqlite_writer_lock_reports_retryable_failures(self) -> None:
        @event.listens_for(self.engine, "connect")
        def short_busy_timeout(connection, record):
            connection.execute("PRAGMA busy_timeout=50")
        self.engine.dispose()
        with self.engine.connect() as blocker:
            blocker.exec_driver_sql("BEGIN IMMEDIATE")
            result = self.post()
            blocker.rollback()
        self.assertEqual((result["issued"], result["skipped"], result["failed"]), (0, 24, 6))
        self.assertTrue(all(row["reason"] == "database_busy_retry_safe" for row in result["results"] if row["outcome"] == "failed"))
        self.assertEqual(self.counts(), (18, 18))
        self.assertEqual(self.post()["issued"], 6)

    def test_courses_and_issuance_are_tenant_scoped(self) -> None:
        for tenant_id in (1, 2):
            response = self.client.get(f"/api/tenants/{tenant_id}/courses")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()), 3)
            self.assertTrue(all(row["tenant_id"] == tenant_id for row in response.json()))
        self.assertEqual(self.client.post(f"/api/tenants/1/courses/{self.course_b}/issue").status_code, 404)
        self.assertEqual(self.client.post(self.url, headers={"X-Tenant-ID": "2"}).status_code, 404)
        self.assertEqual(self.client.post(self.url, json={"tenant_id": 2}).status_code, 422)
        self.assertEqual(self.client.post(self.url, json={"actor": "admin"}).status_code, 422)
        self.assertEqual(self.client.post("/api/tenants/1/courses/0/issue").status_code, 422)
        self.assertEqual(self.client.post("/api/tenants/999/courses/1/issue").status_code, 404)
        self.assertEqual(self.counts(), (18, 18))

    def test_empty_course_and_post_cors(self) -> None:
        with Session(self.engine) as session, session.begin():
            course = Course(tenant_id=1, title="Empty Course")
            session.add(course)
            session.flush()
            course_id = course.id
        result = self.client.post(f"/api/tenants/1/courses/{course_id}/issue").json()
        self.assertEqual((result["total"], result["issued"], result["skipped"], result["failed"]), (0, 0, 0, 0))
        response = self.client.options(self.url, headers={"Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "X-Tenant-ID"})
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
