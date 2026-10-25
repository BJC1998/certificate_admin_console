from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path

from app.database.session import get_path_session
from app.database.tenant_session import TenantSession
from app.schemas.issuance import CourseOption, IssueRequest, IssueSummary
from app.services.issuance import bulk_issue, list_courses

router = APIRouter(prefix="/api/tenants/{tenant_id}/courses", tags=["courses and issuance"])


@router.get("", response_model=list[CourseOption])
def courses(session: Annotated[TenantSession, Depends(get_path_session)]) -> list[CourseOption]:
    return list_courses(session)


@router.post("/{course_id}/issue", response_model=IssueSummary)
def issue(
    course_id: Annotated[int, Path(gt=0)],
    session: Annotated[TenantSession, Depends(get_path_session)],
    body: Annotated[IssueRequest, Body()] = IssueRequest(),
) -> IssueSummary:
    return bulk_issue(session, course_id)
