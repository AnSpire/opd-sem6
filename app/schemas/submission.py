from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class TestAnswerIn(BaseModel):
    question_id: int
    answer: Any


class TestSubmissionCreate(BaseModel):
    answers: list[TestAnswerIn]


class SubmissionOut(BaseModel):
    id: str
    assignment_id: int
    widget_id: int
    board_id: int
    student_user_id: int
    type: str
    attempt_number: int
    submitted_at: datetime
    is_late: bool
    status: str
    payload: dict
    grading: dict
    effective_score: int | None = None

    @field_validator("id", mode="before")
    @classmethod
    def coerce_object_id(cls, v: Any) -> str:
        return str(v)
