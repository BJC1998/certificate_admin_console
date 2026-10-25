"""Pytest workflow regressions complement the existing unittest integration cases."""
import csv
import io

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditAction, AuditLog, Certificate, Course, Enrollment, EnrollmentStatus


@pytest.mark.parametrize("selected,foreign", [(1, 2), (2, 1)])
def test_tenant_boundary_across_all_certificate_endpoints(api_client, isolated_db, selected, foreign):
    def snapshot():
        with Session(isolated_db) as session:
            return (
                session.execute(select(Certificate.__table__).where(Certificate.tenant_id == foreign).order_by(Certificate.id)).all(),
                session.execute(select(AuditLog.__table__).where(AuditLog.tenant_id == foreign).order_by(AuditLog.id)).all(),
            )
    before = snapshot()
    with Session(isolated_db) as session:
        certificate = session.scalar(select(Certificate.id).where(Certificate.tenant_id == foreign).order_by(Certificate.id))
        course = session.scalar(select(Course.id).where(Course.tenant_id == foreign).order_by(Course.id))
    name = "Sydney" if foreign == 1 else "Perth"
    prefix = f"/api/tenants/{selected}"
    listing = api_client.get(f"{prefix}/certificates", params={"search": name})
    assert listing.status_code == 200
    assert listing.json()["total"] == 0
    assert listing.json()["records"] == []
    assert api_client.get(f"{prefix}/certificates/{certificate}").status_code == 404
    assert api_client.post(f"{prefix}/certificates/{certificate}/revoke").status_code == 404
    exported = api_client.get(f"{prefix}/certificates/export", params={"search": name})
    assert exported.status_code == 200
    assert list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig")))) == []
    assert api_client.post(f"{prefix}/courses/{course}/issue").status_code == 404
    # Changing URL while retaining the selected context must fail for every resource shape.
    for suffix in ("certificates", f"certificates/{certificate}", "certificates/export", "courses"):
        assert api_client.get(f"/api/tenants/{foreign}/{suffix}", headers={"X-Tenant-ID": str(selected)}).status_code == 404
    assert snapshot() == before  # Covers state, serials, timestamps and audit history, not only counts.


@pytest.mark.parametrize("field,value", [("tenant_id", 2), ("course_id", 4), ("learner_id", 31),
    ("serial_number", "FORGED"), ("issued_at", "2030-01-01T00:00:00Z"), ("actor", "forged-admin")])
def test_mutation_bodies_cannot_override_ownership_identity_or_actor(api_client, isolated_db, field, value):
    with Session(isolated_db) as session:
        original = session.execute(select(Certificate.__table__).where(Certificate.tenant_id == 1, Certificate.id == 1)).one()
    assert api_client.post("/api/tenants/1/certificates/1/revoke", json={field: value}).status_code == 422
    assert api_client.post("/api/tenants/1/courses/1/issue", json={field: value}).status_code == 422
    with Session(isolated_db) as session:
        assert session.execute(select(Certificate.__table__).where(Certificate.tenant_id == 1, Certificate.id == 1)).one() == original


def test_only_completed_learners_receive_exactly_one_new_certificate_and_audit(api_client, isolated_db):
    with Session(isolated_db) as session:
        enrollments = session.scalars(select(Enrollment).where(Enrollment.tenant_id == 1, Enrollment.course_id == 1)).all()
        completed = {row.learner_id for row in enrollments if row.status == EnrollmentStatus.COMPLETED}
        incomplete = {row.learner_id for row in enrollments if row.status == EnrollmentStatus.INCOMPLETE}
        previous = set(session.scalars(select(Certificate.learner_id).where(Certificate.tenant_id == 1, Certificate.course_id == 1)))
    response = api_client.post("/api/tenants/1/courses/1/issue")
    assert response.status_code == 200
    result = response.json()
    newly_issued = {row["learner_id"] for row in result["results"] if row["outcome"] == "issued"}
    assert newly_issued == completed - previous
    assert all(row["outcome"] == "skipped" and row["reason"] == "enrollment_incomplete"
               for row in result["results"] if row["learner_id"] in incomplete)
    with Session(isolated_db) as session:
        assert list(session.scalars(select(Certificate).where(Certificate.tenant_id == 1,
            Certificate.course_id == 1, Certificate.learner_id.in_(incomplete)))) == []
        for certificate in session.scalars(select(Certificate).where(Certificate.tenant_id == 1,
                Certificate.course_id == 1, Certificate.learner_id.in_(newly_issued))):
            audits = session.scalars(select(AuditLog).where(AuditLog.tenant_id == 1,
                AuditLog.certificate_id == certificate.id, AuditLog.action == AuditAction.ISSUED)).all()
            assert len(audits) == 1
            assert audits[0].actor == "demo-admin-1"
            assert audits[0].created_at == certificate.issued_at


def test_complete_filtered_export_matches_all_list_pages(api_client):
    filters = {"search": "Learner 0", "status": "valid", "sort_by": "issue_date", "sort_order": "asc"}
    serials, page = [], 1
    while True:
        response = api_client.get("/api/tenants/1/certificates", params={**filters, "page": page, "page_size": 2})
        assert response.status_code == 200
        data = response.json()
        serials.extend(row["serial_number"] for row in data["records"])
        if page >= data["total_pages"]:
            break
        page += 1
    assert page > 1 and len(serials) == len(set(serials)) == data["total"]
    exported = api_client.get("/api/tenants/1/certificates/export", params={**filters, "page": page, "page_size": 2})
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert [row["Serial Number"] for row in rows] == serials
