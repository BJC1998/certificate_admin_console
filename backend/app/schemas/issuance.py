from typing import Literal

from pydantic import BaseModel, ConfigDict


class IssueRequest(BaseModel):
    """No client-supplied ownership or actor is accepted."""
    model_config = ConfigDict(extra="forbid")


class CourseOption(BaseModel):
    id: int
    tenant_id: int
    title: str


class LearnerOutcome(BaseModel):
    learner_id: int
    learner_name: str
    outcome: Literal["issued", "skipped", "failed"]
    reason: str
    certificate_id: int | None = None
    serial_number: str | None = None


class IssueSummary(BaseModel):
    tenant_id: int
    course_id: int
    total: int
    issued: int
    skipped: int
    failed: int
    results: list[LearnerOutcome]
