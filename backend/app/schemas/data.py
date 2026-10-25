"""Validated future inputs: tenant_id is never accepted in a request body."""
from pydantic import BaseModel, ConfigDict, Field

from app.models import EnrollmentStatus


class TenantInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CourseInput(TenantInput):
    title: str = Field(min_length=1, max_length=200)


class LearnerInput(TenantInput):
    name: str = Field(min_length=1, max_length=200)


class EnrollmentInput(TenantInput):
    course_id: int = Field(gt=0)
    learner_id: int = Field(gt=0)
    status: EnrollmentStatus = EnrollmentStatus.INCOMPLETE
