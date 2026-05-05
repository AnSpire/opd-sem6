from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.assignment import AssignmentType, FinalScoreStrategy


class AssignmentCreate(BaseModel):
    type: AssignmentType
    title: str
    description: str | None = None
    deadline: datetime | None = None
    allow_late_submissions: bool = False
    max_attempts: int | None = None
    final_score_strategy: FinalScoreStrategy = FinalScoreStrategy.best
    max_score: int


class AssignmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    deadline: datetime | None = None
    allow_late_submissions: bool | None = None
    max_attempts: int | None = None
    final_score_strategy: FinalScoreStrategy | None = None
    max_score: int | None = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    widget_id: int
    creator_user_id: int
    type: AssignmentType
    title: str
    description: str | None
    deadline: datetime | None
    allow_late_submissions: bool
    max_attempts: int | None
    final_score_strategy: FinalScoreStrategy
    max_score: int
    created_at: datetime
    updated_at: datetime


class AssignmentPreview(BaseModel):
    id: int
    title: str
    type: AssignmentType
    deadline: datetime | None
    created_at: datetime


class WidgetConfigOut(BaseModel):
    assignments_count: int
    preview: list[AssignmentPreview]


class AssignmentWithConfigOut(BaseModel):
    assignment: AssignmentOut
    config: WidgetConfigOut


class ConfigOut(BaseModel):
    config: WidgetConfigOut
