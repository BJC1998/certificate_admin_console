"""Details and revocation integration tests on real, isolated SQLite files."""
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
from app.models import AuditAction, AuditLog, Certificate, CertificateStatus
from app.services import certificate_details


class CertificateDetailTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_root = Path(__file__).resolve().parents[2] / "tmp"
        temp_root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temp_root)
        self.engine = create_sqlite_engine(f"sqlite:///{Path(self.directory.name).as_posix()}/details.db")
        seed_database(self.engine)
        self.patches = [patch("app.core.tenant.engine", self.engine),
            patch("app.database.session.SessionLocal", side_effect=lambda **kwargs: TenantSession(self.engine, **kwargs))]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)
        with Session(self.engine) as session:
            self.certificate_id = session.scalar(select(Certificate.id).where(Certificate.tenant_id == 1,
                Certificate.status == CertificateStatus.VALID).order_by(Certificate.id))
            self.foreign_id = session.scalar(select(Certificate.id).where(Certificate.tenant_id == 2).order_by(Certificate.id))
            self.revoked_id = session.scalar(select(Certificate.id).where(Certificate.tenant_id == 1,
                Certificate.status == CertificateStatus.REVOKED).order_by(Certificate.id))
        self.url = f"/api/tenants/1/certificates/{self.certificate_id}"

    def tearDown(self) -> None:
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()
        self.directory.cleanup()

    def audit_rows(self, certificate_id=None) -> list:
        with Session(self.engine) as session:
            return session.execute(select(AuditLog.id, AuditLog.actor, AuditLog.created_at).where(
                AuditLog.tenant_id == 1, AuditLog.certificate_id == (certificate_id or self.certificate_id),
                AuditLog.action == AuditAction.REVOKED)).all()

    def test_valid_detail_contract_and_local_date(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["status"], "valid")
        self.assertEqual(data["serial_number"], "OCEAN-DEMO-1-1-001")
        self.assertEqual(data["learner_name"], "Sydney Learner 01")
        self.assertEqual(data["course_title"], "Workplace Safety")
        self.assertEqual(data["tenant_name"], "Sydney")
        self.assertEqual(data["tenant_timezone"], "Australia/Sydney")
        self.assertEqual(data["issued_at"], "2026-09-27T01:30:00+10:00")
        self.assertEqual(self.audit_rows(), [])

    def test_perth_and_sydney_dst_dates(self) -> None:
        data = self.client.get(f"/api/tenants/2/certificates/{self.foreign_id}").json()
        self.assertEqual(data["issued_at"], "2026-09-26T23:30:00+08:00")
        with Session(self.engine) as session:
            certificate_id = session.scalar(select(Certificate.id).where(Certificate.tenant_id == 1,
                Certificate.serial_number == "OCEAN-DEMO-1-1-010"))
        self.assertEqual(self.client.get(f"/api/tenants/1/certificates/{certificate_id}").json()["issued_at"],
                         "2026-10-06T02:30:00+11:00")

    def test_revoke_repeat_preserves_identity_and_writes_one_audit(self) -> None:
        original = self.client.get(self.url).json()
        updates = []
        @event.listens_for(self.engine, "before_cursor_execute")
        def count_updates(connection, cursor, statement, parameters, context, many):
            if statement.startswith("UPDATE certificates"):
                updates.append(statement)
        first = self.client.post(self.url + "/revoke")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["changed"])
        revoked = first.json()["certificate"]
        self.assertEqual(revoked, {**original, "status": "revoked"})
        audits = self.audit_rows()
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].actor, "demo-admin-1")
        self.assertEqual(audits[0].created_at.utcoffset().total_seconds(), 0)
        second = self.client.post(self.url + "/revoke")
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["changed"])
        self.assertEqual(second.json()["certificate"], revoked)
        self.assertEqual(self.audit_rows(), audits)
        self.assertEqual(len(updates), 1)
        self.assertEqual(self.client.get(self.url).json(), revoked)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Certificate)), 108)
        print("EVIDENCE revoke/repeat: one state UPDATE, one revoke audit, unchanged serial/issued_at/id, 108 certificates retained")

    def test_already_revoked_seed_record_is_unchanged(self) -> None:
        url = f"/api/tenants/1/certificates/{self.revoked_id}"
        before = self.client.get(url).json()
        audits = self.audit_rows(self.revoked_id)
        result = self.client.post(url + "/revoke")
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()["changed"])
        self.assertEqual(result.json()["certificate"], before)
        self.assertEqual(self.audit_rows(self.revoked_id), audits)

    def test_audit_failure_rolls_back_status_and_retry_recovers(self) -> None:
        def fail_audit(mapper, connection, target):
            if target.action == AuditAction.REVOKED:
                raise IntegrityError("Injected revoke audit failure", {}, Exception("test failure"))
        event.listen(AuditLog, "before_insert", fail_audit)
        try:
            response = self.client.post(self.url + "/revoke")
        finally:
            event.remove(AuditLog, "before_insert", fail_audit)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get(self.url).json()["status"], "valid")
        self.assertEqual(self.audit_rows(), [])
        self.assertTrue(self.client.post(self.url + "/revoke").json()["changed"])
        self.assertEqual(len(self.audit_rows()), 1)

    def test_bulk_issue_after_revocation_never_reissues_target(self) -> None:
        original = self.client.get(self.url).json()
        self.assertEqual(self.client.post(self.url + "/revoke").status_code, 200)
        response = self.client.post(f"/api/tenants/1/courses/{original['course_id']}/issue")
        self.assertEqual(response.status_code, 200)
        outcome = next(row for row in response.json()["results"] if row["learner_id"] == original["learner_id"])
        self.assertEqual((outcome["outcome"], outcome["reason"], outcome["certificate_id"]),
                         ("skipped", "previously_revoked", self.certificate_id))
        self.assertEqual(self.client.get(self.url).json(), {**original, "status": "revoked"})
        with Session(self.engine) as session:
            count = session.scalar(select(func.count()).select_from(Certificate).where(Certificate.tenant_id == 1,
                Certificate.course_id == original["course_id"], Certificate.learner_id == original["learner_id"]))
            self.assertEqual(count, 1)
        self.assertEqual(len(self.audit_rows()), 1)

    def test_missing_cross_tenant_and_invalid_requests(self) -> None:
        for path in (f"/api/tenants/1/certificates/{self.foreign_id}", "/api/tenants/1/certificates/999999",
                     f"/api/tenants/999/certificates/{self.certificate_id}"):
            self.assertEqual(self.client.get(path).status_code, 404)
            self.assertEqual(self.client.post(path + "/revoke").status_code, 404)
        for method, path in (("get", self.url), ("post", self.url + "/revoke")):
            self.assertEqual(getattr(self.client, method)(path, headers={"X-Tenant-ID": "2"}).status_code, 404)
        self.assertEqual(self.client.post(self.url + "/revoke", json={"tenant_id": 2}).status_code, 422)
        self.assertEqual(self.client.post(self.url + "/revoke", json={"actor": "admin"}).status_code, 422)
        for value in ("0", "-1", "abc", "9223372036854775808"):
            path = f"/api/tenants/1/certificates/{value}"
            self.assertEqual(self.client.get(path).status_code, 422)
            self.assertEqual(self.client.post(path + "/revoke").status_code, 422)
        self.assertEqual(self.audit_rows(), [])

    def test_concurrent_revoke_commits_one_audit(self) -> None:
        barrier = threading.Barrier(2)
        seen = set()
        lock = threading.Lock()
        original = certificate_details.get_tenant_record
        conflicts = []
        def lookup(session, model, record_id):
            record = original(session, model, record_id)
            wait = False
            if record.status == CertificateStatus.VALID:
                with lock:
                    if threading.get_ident() not in seen:
                        seen.add(threading.get_ident())
                        wait = True
            if wait:
                barrier.wait(timeout=15)
            return record
        @event.listens_for(self.engine, "handle_error")
        def observe_error(context):
            conflicts.append(getattr(context.original_exception, "sqlite_errorcode", None))
        def request():
            with TestClient(app) as client:
                response = client.post(self.url + "/revoke")
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()
        with patch.object(certificate_details, "get_tenant_record", side_effect=lookup):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(request) for _ in range(2)]
                results = [future.result(timeout=30) for future in futures]
        self.assertEqual(sum(row["changed"] for row in results), 1)
        self.assertTrue(all(row["certificate"]["status"] == "revoked" for row in results))
        self.assertEqual(len(self.audit_rows()), 1)
        self.assertIn(sqlite3.SQLITE_CONSTRAINT_UNIQUE, conflicts)
        print(f"EVIDENCE concurrent revoke: changed={[row['changed'] for row in results]}, one revoke audit; SQLite conflicts={conflicts}")

    def test_lost_response_after_revoke_commit_is_safe_to_repeat(self) -> None:
        async def lose_response(scope, receive, send):
            if scope["type"] == "http" and scope["method"] == "POST":
                async def discard(message):
                    pass
                await app(scope, receive, discard)
                raise ConnectionResetError("Revocation committed; response lost")
            await app(scope, receive, send)
        with TestClient(lose_response) as client:
            with self.assertRaises(ConnectionResetError):
                client.post(self.url + "/revoke")
        self.assertEqual(self.client.get(self.url).json()["status"], "revoked")
        self.assertFalse(self.client.post(self.url + "/revoke").json()["changed"])
        self.assertEqual(len(self.audit_rows()), 1)


if __name__ == "__main__":
    unittest.main()
