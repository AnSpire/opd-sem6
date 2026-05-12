from pydantic import BaseModel, ConfigDict


class HomeworkDetailsCreate(BaseModel):
    prompt: str
    reference_answer: str | None = None
    grading_criteria: str | None = None
    accepted_formats: list[str] = []


class HomeworkDetailsUpdate(BaseModel):
    prompt: str | None = None
    reference_answer: str | None = None
    grading_criteria: str | None = None
    accepted_formats: list[str] | None = None


class HomeworkDetailsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: int
    prompt: str
    reference_answer: str | None
    grading_criteria: str | None
    accepted_formats: list[str]
