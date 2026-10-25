import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.engine import create_sqlite_engine
from app.database.seed import seed_database
from app.database.tenant_session import TenantSession
from app.main import app
from app.models import Certificate


class CertificateListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sqlite_engine("sqlite://", poolclass=StaticPool)
        seed_database(self.engine)
        self.patches = [
            patch("app.core.tenant.engine", self.engine),
            patch("app.routers.tenants.engine", self.engine),
            patch("app.database.session.SessionLocal", side_effect=lambda **kwargs: TenantSession(self.engine, **kwargs)),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()

    def get_page(self, tenant_id: int = 1, **params: object) -> dict:
        response = self.client.get(f"/api/tenants/{tenant_id}/certificates", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_default_contract_and_no_write_side_effects(self) -> None:
        page = self.get_page()
        self.assertEqual((page["total"], page["page"], page["page_size"], page["total_pages"]), (54, 1, 10, 6))
        self.assertEqual(page["tenant_timezone"], "Australia/Sydney")
        self.assertEqual(len(page["records"]), 10)
        self.assertEqual(set(page["records"][0]), {"id", "tenant_id", "learner_name", "course_title", "serial_number", "issued_at", "status"})
        with Session(self.engine) as session:
            certificate = session.get(Certificate, page["records"][0]["id"])
            self.assertEqual(certificate.issued_at.utcoffset().total_seconds(), 0)

    def test_learner_search_is_trimmed_and_case_insensitive(self) -> None:
        page = self.get_page(search="  sYdNeY lEaRnEr 01  ")
        self.assertEqual(page["total"], 3)
        self.assertTrue(all(record["learner_name"] == "Sydney Learner 01" for record in page["records"]))

    def test_serial_search(self) -> None:
        page = self.get_page(search="ocean-demo-1-2-005")
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["records"][0]["serial_number"], "OCEAN-DEMO-1-2-005")

    def test_no_results_and_literal_wildcards(self) -> None:
        for search in ("not a learner", "%", "_", "Sydney' OR 1=1--", "\\"):
            with self.subTest(search=search):
                page = self.get_page(search=search)
                self.assertEqual((page["records"], page["total"], page["total_pages"]), ([], 0, 0))

    def test_every_page_is_complete_and_has_no_duplicates(self) -> None:
        ids = []
        for number in range(1, 9):
            page = self.get_page(page=number, page_size=7)
            self.assertEqual(page["total_pages"], 8)
            ids.extend(record["id"] for record in page["records"])
        self.assertEqual(len(ids), 54)
        self.assertEqual(len(set(ids)), 54)
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_out_of_range_page_has_empty_records_and_unchanged_count(self) -> None:
        page = self.get_page(page=100)
        self.assertEqual((page["records"], page["total"], page["page"]), ([], 54, 100))

    def test_all_sort_fields_both_directions_and_deterministic_ties(self) -> None:
        for field in ("learner_name", "course_title", "serial_number", "issued_at", "status"):
            with self.subTest(field=field):
                ascending = self.get_page(sort_by=field, sort_order="asc", page_size=100)["records"]
                descending = self.get_page(sort_by=field, sort_order="desc", page_size=100)["records"]
                self.assertEqual([row["id"] for row in descending], [row["id"] for row in reversed(ascending)])
                self.assertEqual([row[field] for row in ascending], sorted(row[field] for row in ascending))
                self.assertEqual(ascending, self.get_page(sort_by=field, sort_order="asc", page_size=100)["records"])
        # Three courses share each learner name: a page boundary must keep stable tie order.
        first = self.get_page(sort_by="learner_name", sort_order="asc", page_size=2)["records"]
        second = self.get_page(sort_by="learner_name", sort_order="asc", page_size=2, page=2)["records"]
        self.assertEqual([row["id"] for row in first + second], [1, 2, 3, 4])

    def test_tenant_isolation_applies_to_records_search_and_total(self) -> None:
        for tenant_id, name in ((1, "Sydney"), (2, "Perth"), (1, "Sydney")):
            page = self.get_page(tenant_id, page_size=100)
            self.assertEqual(page["total"], 54)
            self.assertTrue(all(row["tenant_id"] == tenant_id and row["learner_name"].startswith(name) for row in page["records"]))
        self.assertEqual(self.get_page(1, search="Perth")["total"], 0)
        self.assertEqual(self.get_page(2, search="OCEAN-DEMO-1")["total"], 0)

    def test_tenant_local_offsets_include_dst_and_perth(self) -> None:
        self.assertEqual(self.get_page(search="OCEAN-DEMO-1-1-001")["records"][0]["issued_at"], "2026-09-27T01:30:00+10:00")
        self.assertEqual(self.get_page(search="OCEAN-DEMO-1-1-010")["records"][0]["issued_at"], "2026-10-06T02:30:00+11:00")
        self.assertEqual(self.get_page(2, search="OCEAN-DEMO-2-1-001")["records"][0]["issued_at"], "2026-09-26T23:30:00+08:00")

    def test_invalid_parameters_return_422(self) -> None:
        for params in ({"page": 0}, {"page": -1}, {"page": "abc"}, {"page": 1_000_001},
                       {"page_size": 0}, {"page_size": 101}, {"page_size": "1.5"},
                       {"sort_by": "DROP TABLE certificates"}, {"sort_order": "sideways"}, {"search": "a" * 201}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/tenants/1/certificates", params=params).status_code, 422)
        self.assertEqual(self.client.get("/api/tenants/0/certificates").status_code, 422)

    def test_unknown_tenant_and_conflicting_header_return_404(self) -> None:
        self.assertEqual(self.client.get("/api/tenants/999/certificates").status_code, 404)
        response = self.client.get("/api/tenants/2/certificates", headers={"X-Tenant-ID": "1"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Resource not found"})
        self.assertEqual(self.client.get("/api/tenants/1/certificates", headers={"X-Tenant-ID": "1"}).status_code, 200)

    def test_tenant_directory_exposes_only_demo_metadata(self) -> None:
        response = self.client.get("/api/tenants")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()], [1, 2])
        self.assertTrue(all(set(row) == {"id", "name", "timezone"} for row in response.json()))


if __name__ == "__main__":
    unittest.main()
