from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.question import QuestionType, ShortTextMatch


class QuestionCreate(BaseModel):
    order: int
    text: str
    type: QuestionType
    options: list[str] | None = None
    correct_answer: Any
    points: int
    short_text_match: ShortTextMatch = ShortTextMatch.exact


class QuestionUpdate(BaseModel):
    order: int | None = None
    text: str | None = None
    type: QuestionType | None = None
    options: list[str] | None = None
    correct_answer: Any | None = None
    points: int | None = None
    short_text_match: ShortTextMatch | None = None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assignment_id: int
    order: int
    text: str
    type: QuestionType
    options: Any | None
    correct_answer: Any | None
    points: int
    short_text_match: ShortTextMatch | None
