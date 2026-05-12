import asyncio
from functools import partial

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import settings
from app.models.assignment import Assignment
from app.models.homework_details import HomeworkDetails
from app.services import storage

_genai_client: genai.Client | None = None


def get_genai_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        http_options = types.HttpOptions(proxy=settings.proxy_url) if settings.proxy_url else None
        _genai_client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=http_options,
        )
    return _genai_client


class RubricItem(BaseModel):
    criterion: str
    points: int
    max_points: int
    comment: str


class GradingResult(BaseModel):
    score: int
    feedback: str
    rubric_breakdown: list[RubricItem]


def _build_prompt(
    hw_details: HomeworkDetails,
    assignment: Assignment,
    submission: dict,
) -> str:
    student_text = submission["payload"].get("text", "") or ""
    student_markdown = submission["payload"].get("markdown", "") or ""
    student_answer = student_text or student_markdown or "(текст не предоставлен)"

    ref = f"\nЭталонный ответ (если есть): {hw_details.reference_answer}" if hw_details.reference_answer else ""
    criteria = f"\nКритерии оценки: {hw_details.grading_criteria}" if hw_details.grading_criteria else ""

    return (
        f"Ты — эксперт-проверяющий. Оцени ответ ученика на задание.\n\n"
        f"Задание: {hw_details.prompt}{ref}{criteria}\n"
        f"Максимальный балл: {assignment.max_score}\n\n"
        f"Ответ ученика:\n{student_answer}"
    )


async def grade_homework(
    submission: dict,
    hw_details: HomeworkDetails,
    assignment: Assignment,
) -> GradingResult:
    client = get_genai_client()
    prompt_text = _build_prompt(hw_details, assignment, submission)

    parts: list[types.Part] = [types.Part.from_text(text=prompt_text)]

    for att in submission["payload"].get("attachments", []):
        data = await storage.download_object(att["s3_key"])
        parts.append(types.Part.from_bytes(data=data, mime_type=att["mime"]))

    loop = asyncio.get_running_loop()
    fn = partial(
        client.models.generate_content,
        model="gemini-2.5-flash",
        contents=[types.Content(parts=parts)],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GradingResult,
            temperature=0.2,
        ),
    )
    response = await loop.run_in_executor(None, fn)

    result: GradingResult | None = response.parsed
    if result is None:
        raise ValueError(f"Gemini returned unparseable response: {response.text!r}")

    return result
