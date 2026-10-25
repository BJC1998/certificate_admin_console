"""CSV correctness, shared filtering, failure cleanup and bounded-memory export."""
import asyncio
import csv
import gc
import io
import sys
import tempfile
import tracemalloc
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import event, insert, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.engine import create_sqlite_engine
from app.database.seed import seed_database
from app.database.tenant_session import TenantSession
from app.main import app
from app.models import AuditAction, AuditLog, Certificate, CertificateStatus, Course, Enrollment, EnrollmentStatus, Learner
from app.routers.certificates import CSVExportResponse
from app.schemas.certificates import CertificateExportQuery
from app.services import certificate_export


class CertificateExportTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[2] / "tmp"
        root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=root)
        self.engine = create_sqlite_engine(f"sqlite:///{Path(self.directory.name).as_posix()}/export.db")
        seed_database(self.engine)
        self.patches = [patch("app.core.tenant.engine", self.engine),
            patch("app.database.session.SessionLocal", side_effect=lambda **kwargs: TenantSession(self.engine, **kwargs))]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()
        self.directory.cleanup()

    def export(self, tenant=1, **params):
        response = self.client.get(f"/api/tenants/{tenant}/certificates/export", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"), newline="")))
        return response, rows

    def test_headers_all_matches_not_current_page_and_no_route_collision(self) -> None:
        response, rows = self.export(page=2, page_size=1)
        self.assertEqual(len(rows), 54)
        self.assertEqual(list(rows[0]), list(certificate_export.CSV_HEADERS))
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(int(response.headers["content-length"]), len(response.content))
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("certificates-sydney-tenant-1-all-", response.headers["content-disposition"])
        self.assertEqual(len({row["Serial Number"] for row in rows}), 54)

    def test_name_serial_and_combined_status_filter_reuse_list_rules(self) -> None:
        for params in ({"search": "  sydney learner 01 "}, {"search": "OCEAN-DEMO-1-2-005"},
                       {"status": "revoked"}, {"status": "valid", "search": "Learner 01"}):
            with self.subTest(params=params):
                _, rows = self.export(**params)
                listing = self.client.get("/api/tenants/1/certificates", params={**params, "page_size": 100}).json()
                self.assertEqual(len(rows), listing["total"])
                self.assertEqual([row["Serial Number"] for row in rows], [row["serial_number"] for row in listing["records"]])
        self.assertEqual(len(self.export(search="Sydney Learner 01")[1]), 3)
        self.assertEqual(len(self.export(search="OCEAN-DEMO-1-2-005")[1]), 1)
        self.assertEqual(len(self.export(status="revoked")[1]), 9)

    def test_tenant_isolation_and_literal_search(self) -> None:
        for tenant, name in ((1, "Sydney"), (2, "Perth")):
            _, rows = self.export(tenant)
            self.assertEqual(len(rows), 54)
            self.assertTrue(all(row["Learner Name"].startswith(name) for row in rows))
        for value in ("Perth", "OCEAN-DEMO-2", "%", "_", "not found"):
            self.assertEqual(self.export(search=value)[1], [])

    def test_empty_export_contains_only_valid_headers(self) -> None:
        response, rows = self.export(search="no results")
        self.assertEqual(rows, [])
        self.assertEqual(response.content.decode("utf-8-sig"), "Learner Name,Course Title,Serial Number,Issue Date\r\n")

    def test_all_allowlisted_sorts_match_list_and_are_stable(self) -> None:
        for field in ("learner_name", "course_title", "serial_number", "issued_at", "issue_date", "status"):
            for order in ("asc", "desc"):
                with self.subTest(field=field, order=order):
                    _, rows = self.export(sort_by=field, sort_order=order)
                    listing = self.client.get("/api/tenants/1/certificates", params={
                        "sort_by": field, "sort_order": order, "page_size": 100}).json()
                    self.assertEqual([row["Serial Number"] for row in rows], [row["serial_number"] for row in listing["records"]])

    def test_dst_transition_local_dates_and_date_tie_breaker(self) -> None:
        with Session(self.engine) as session, session.begin():
            for certificate_id, timestamp in ((1, datetime(2026, 10, 3, 16, 0, tzinfo=UTC)),
                    (2, datetime(2026, 10, 3, 15, 59, tzinfo=UTC)), (3, datetime(2026, 10, 3, 13, 30, tzinfo=UTC))):
                certificate = session.scalar(select(Certificate).where(Certificate.tenant_id == 1, Certificate.id == certificate_id))
                certificate.issued_at = timestamp
        _, rows = self.export(search="Sydney Learner 01", sort_by="issue_date", sort_order="asc")
        self.assertEqual([row["Serial Number"] for row in rows], ["OCEAN-DEMO-1-3-001", "OCEAN-DEMO-1-1-001", "OCEAN-DEMO-1-2-001"])
        dates = {row["Serial Number"]: row["Issue Date"] for row in rows}
        self.assertEqual(dates["OCEAN-DEMO-1-1-001"], "2026-10-04T03:00:00+11:00")
        self.assertEqual(dates["OCEAN-DEMO-1-2-001"], "2026-10-04T01:59:00+10:00")
        self.assertEqual(dates["OCEAN-DEMO-1-3-001"], "2026-10-03T23:30:00+10:00")
        _, chronological = self.export(search="Sydney Learner 01", sort_by="issued_at", sort_order="asc")
        self.assertEqual([row["Serial Number"] for row in chronological], ["OCEAN-DEMO-1-3-001", "OCEAN-DEMO-1-2-001", "OCEAN-DEMO-1-1-001"])
        self.assertEqual(self.export(2, search="OCEAN-DEMO-2-1-001")[1][0]["Issue Date"], "2026-09-26T23:30:00+08:00")

    def test_utf8_quotes_commas_and_embedded_newlines_round_trip(self) -> None:
        name, title = '张三, "Ops"\nSecond line', 'Security, "Safety"\r\n培训'
        with Session(self.engine) as session, session.begin():
            learner = session.scalar(select(Learner).where(Learner.tenant_id == 1, Learner.id == 1))
            course = session.scalar(select(Course).where(Course.tenant_id == 1, Course.id == 1))
            learner.name, course.title = name, title
        _, rows = self.export(search="OCEAN-DEMO-1-1-001")
        self.assertEqual(rows[0]["Learner Name"], name)
        self.assertEqual(rows[0]["Course Title"], title)
        self.assertEqual(len(rows), 1)

    def test_formula_injection_is_neutralized_for_all_text_columns(self) -> None:
        for text in ("=1+1", "+cmd", "-1+2", "@SUM(A1)", "  =1+1", "\ttext", "\rtext", "\ntext", "\ufeff  =1+1", "\u2003=1+1"):
            self.assertEqual(certificate_export.csv_text(text), "'" + text)
        with Session(self.engine) as session, session.begin():
            session.scalar(select(Learner).where(Learner.tenant_id == 1, Learner.id == 1)).name = "=1+1"
            session.scalar(select(Course).where(Course.tenant_id == 1, Course.id == 1)).title = "  +cmd"
            session.scalar(select(Certificate).where(Certificate.tenant_id == 1, Certificate.id == 1)).serial_number = "@SUM(1,2)"
        _, rows = self.export(search="@SUM(1,2)")
        self.assertEqual([rows[0][key] for key in certificate_export.CSV_HEADERS[:3]], ["'=1+1", "'  +cmd", "'@SUM(1,2)"])

    def test_invalid_requests_unknown_tenants_and_header_conflicts(self) -> None:
        for params in ({"sort_by": "invalid"}, {"sort_order": "invalid"}, {"status": "deleted"}, {"search": "a" * 201}):
            self.assertEqual(self.client.get("/api/tenants/1/certificates/export", params=params).status_code, 422)
        for value in ("0", "-1", "abc", "9223372036854775808"):
            self.assertEqual(self.client.get(f"/api/tenants/{value}/certificates/export").status_code, 422)
        self.assertEqual(self.client.get("/api/tenants/999/certificates/export").status_code, 404)
        self.assertEqual(self.client.get("/api/tenants/1/certificates/export", headers={"X-Tenant-ID": "2"}).status_code, 404)

    def test_failure_during_later_batch_returns_error_not_partial_csv(self) -> None:
        original_execute = TenantSession.execute
        factory = certificate_export.tempfile.SpooledTemporaryFile
        files = []
        def spool(*args, **kwargs):
            file = factory(*args, **kwargs)
            files.append(file)
            return file
        class FailedResult:
            def __init__(self, result): self.result = result
            def partitions(self, size):
                for batch in self.result.partitions(size):
                    yield batch
                    raise OperationalError("Simulated fetch failure", {}, Exception("test failure"))
            def close(self): self.result.close()
        def execute(session, statement, *args, **kwargs):
            result = original_execute(session, statement, *args, **kwargs)
            return FailedResult(result) if statement.get_execution_options().get("yield_per") else result
        with patch.object(TenantSession, "execute", new=execute), patch.object(certificate_export.tempfile, "SpooledTemporaryFile", side_effect=spool):
            response = self.client.get("/api/tenants/1/certificates/export")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("content-disposition", response.headers)
        self.assertTrue(all(file.closed for file in files))

    def test_database_failure_resolving_context_returns_503(self) -> None:
        with patch("app.core.tenant.engine.connect", side_effect=OperationalError("Unavailable", {}, Exception("test"))):
            self.assertEqual(self.client.get("/api/tenants/1/certificates/export").status_code, 503)

    def test_response_disconnect_closes_prepared_file(self) -> None:
        with TenantSession(self.engine, tenant_id=1) as session:
            prepared = certificate_export.prepare_export(session, CertificateExportQuery())
        response = CSVExportResponse(prepared)
        async def disconnected_send(message): raise RuntimeError("Simulated disconnected download")
        async def receive(): return {"type": "http.disconnect"}
        with self.assertRaises(RuntimeError):
            asyncio.run(response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, disconnected_send))
        self.assertTrue(prepared.file.closed)

    def test_large_dataset_uses_batched_reads_and_rolls_to_disk(self) -> None:
        count, timestamp = 25_000, datetime(2026, 10, 3, 16, 0, tzinfo=UTC)
        with Session(self.engine) as session, session.begin():
            session.add(Course(id=1000, tenant_id=1, title="Scale test " + "培" * 180))
            session.flush()
            for start in range(0, count, 500):
                ids = range(1000 + start, 1000 + min(start + 500, count))
                session.execute(insert(Learner), [{"id": i, "tenant_id": 1, "name": f"Scale learner {i:05d}"} for i in ids])
                session.execute(insert(Enrollment), [{"id": i, "tenant_id": 1, "course_id": 1000, "learner_id": i, "status": EnrollmentStatus.COMPLETED} for i in ids])
                session.execute(insert(Certificate), [{"id": i, "tenant_id": 1, "course_id": 1000, "learner_id": i, "serial_number": f"SCALE-{i:05d}", "issued_at": timestamp, "status": CertificateStatus.VALID} for i in ids])
                session.execute(insert(AuditLog), [{"id": i, "tenant_id": 1, "certificate_id": i, "course_id": 1000, "learner_id": i, "action": AuditAction.ISSUED, "actor": "scale-fixture", "created_at": timestamp} for i in ids])
        options = []
        @event.listens_for(self.engine, "before_cursor_execute")
        def observe(connection, cursor, statement, parameters, context, many):
            if context.execution_options.get("yield_per"):
                options.append((context.execution_options["yield_per"], statement))
        gc.collect()
        tracemalloc.start()
        with TenantSession(self.engine, tenant_id=1) as session:
            prepared = certificate_export.prepare_export(session, CertificateExportQuery(search="Scale learner"))
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        try:
            self.assertEqual(prepared.row_count, count)
            self.assertTrue(getattr(prepared.file, "_rolled"))
            self.assertLess(peak, 8 * 1024 * 1024)
            self.assertLess(peak * 2, prepared.size)
            self.assertEqual(options[0][0], 500)
            self.assertNotIn("OFFSET", options[0][1])
            reader = csv.reader(io.TextIOWrapper(prepared.file, encoding="utf-8-sig", newline=""))
            self.assertEqual(next(reader), list(certificate_export.CSV_HEADERS))
            self.assertEqual(sum(1 for _ in reader), count)
            print(f"EVIDENCE export scale: {count} rows, CSV={prepared.size} bytes, Python peak={peak} bytes, yield_per=500, disk spool=True")
        finally:
            prepared.close()


if __name__ == "__main__":
    unittest.main()
