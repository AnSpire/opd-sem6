from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from bson import ObjectId

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.services.ai_grader import GradingResult, RubricItem
from app.workers.arq_worker import grade_submission

from tests.conftest import TEACHER_HEADERS, STUDENT_HEADERS

HW_ASSIGNMENT_PAYLOAD = {
    "type": "homework",
    "title": "Worker Test Essay",
    "max_score": 10,
    "final_score_strategy": "last",
}
HW_DETAILS_PAYLOAD = {
    "prompt": "Explain something",
    "accepted_formats": ["text"],
}


def _fake_grading_result(score=8):
    return GradingResult(
        score=score,
        feedback="Well done",
        rubric_breakdown=[RubricItem(criterion="Overall", points=score, max_points=10, comment="Good")],
    )


@pytest_asyncio.fixture
async def hw_assignment(client, widget):
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json=HW_ASSIGNMENT_PAYLOAD,
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 201
    return r.json()["assignment"]


@pytest_asyncio.fixture
async def hw_submission(client, hw_assignment):
    await client.put(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )
    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            data={"text": "My homework answer"},
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 201
    return r.json()


def _make_ctx():
    from app.db.mongo import get_db
    from app.db.postgres import AsyncSessionLocal
    return {
        "db": get_db(),
        "session_factory": AsyncSessionLocal,
    }


# ---------------------------------------------------------------------------
# grade_submission — successful path
# ---------------------------------------------------------------------------

async def test_grade_submission_success(hw_submission):
    ctx = _make_ctx()
    submission_id = hw_submission["id"]

    with patch("app.workers.arq_worker.ai_grader.grade_homework", new_callable=AsyncMock,
               return_value=_fake_grading_result(8)):
        await grade_submission(ctx, submission_id)

    from app.db.mongo import get_db
    from app.repositories.submissions import get_by_id
    doc = await get_by_id(get_db(), submission_id)

    assert doc["status"] == "pending_teacher"
    assert doc["grading"]["ai"] is not None
    assert doc["grading"]["ai"]["score"] == 8
    assert doc["grading"]["ai"]["feedback"] == "Well done"


# ---------------------------------------------------------------------------
# grade_submission — parse error path
# ---------------------------------------------------------------------------

async def test_grade_submission_parse_error(hw_submission):
    ctx = _make_ctx()
    submission_id = hw_submission["id"]

    with patch("app.workers.arq_worker.ai_grader.grade_homework", new_callable=AsyncMock,
               side_effect=ValueError("Gemini returned unparseable response")):
        await grade_submission(ctx, submission_id)

    from app.db.mongo import get_db
    from app.repositories.submissions import get_by_id
    from app.repositories.ai_logs import create_log
    doc = await get_by_id(get_db(), submission_id)

    assert doc["status"] == "pending_teacher"
    assert doc["grading"]["ai"] is None

    log = await get_db().ai_logs.find_one({"submission_id": submission_id})
    assert log is not None
    assert log["status"] == "parse_error"
    assert "unparseable" in log["error"]


# ---------------------------------------------------------------------------
# grade_submission — api error path
# ---------------------------------------------------------------------------

async def test_grade_submission_api_error(hw_submission):
    ctx = _make_ctx()
    submission_id = hw_submission["id"]

    with patch("app.workers.arq_worker.ai_grader.grade_homework", new_callable=AsyncMock,
               side_effect=RuntimeError("API unavailable")):
        await grade_submission(ctx, submission_id)

    from app.db.mongo import get_db
    from app.repositories.submissions import get_by_id
    doc = await get_by_id(get_db(), submission_id)

    assert doc["status"] == "pending_teacher"
    log = await get_db().ai_logs.find_one({"submission_id": submission_id})
    assert log["status"] == "api_error"


# ---------------------------------------------------------------------------
# grade_submission — submission not found
# ---------------------------------------------------------------------------

async def test_grade_submission_not_found():
    ctx = _make_ctx()
    nonexistent_id = str(ObjectId())
    # Should complete without raising
    await grade_submission(ctx, nonexistent_id)
