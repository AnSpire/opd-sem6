from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio(loop_scope="session")

from tests.conftest import TEACHER_HEADERS, STUDENT_HEADERS, OTHER_TEACHER_HEADERS

HW_ASSIGNMENT_PAYLOAD = {
    "type": "homework",
    "title": "Grade Test Essay",
    "max_score": 10,
    "final_score_strategy": "last",
}
HW_DETAILS_PAYLOAD = {
    "prompt": "Explain OOP",
    "accepted_formats": ["text"],
}
FAKE_AI_GRADING = {
    "score": 8,
    "max_score": 10,
    "feedback": "Good work",
    "rubric_breakdown": [{"criterion": "Overall", "points": 8, "max_points": 10, "comment": "Fine"}],
    "graded_at": None,
    "log_id": None,
}


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
async def hw_submission_raw(client, hw_assignment):
    """Homework submission in pending_ai state (no worker)."""
    await client.put(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )
    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            data={"text": "My answer"},
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 201
    return r.json()


@pytest_asyncio.fixture
async def hw_submission_ai_graded(hw_submission_raw):
    """Simulate worker: write grading.ai and set status=pending_teacher."""
    from app.repositories.submissions import update_grading
    from app.db.mongo import get_db
    await update_grading(get_db(), hw_submission_raw["id"], "pending_teacher", FAKE_AI_GRADING)
    return hw_submission_raw


# ---------------------------------------------------------------------------
# accept_ai=true
# ---------------------------------------------------------------------------

async def test_grade_accept_ai(client, hw_submission_ai_graded):
    r = await client.patch(
        f"/api/v1/submissions/{hw_submission_ai_graded['id']}/grade",
        json={"accept_ai": True},
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "graded"
    assert data["grading"]["final"]["score"] == FAKE_AI_GRADING["score"]
    assert data["grading"]["final"]["feedback"] == FAKE_AI_GRADING["feedback"]
    assert data["grading"]["final"]["accepted_ai"] is True
    assert data["effective_score"] == FAKE_AI_GRADING["score"]


# ---------------------------------------------------------------------------
# accept_ai=false with custom score
# ---------------------------------------------------------------------------

async def test_grade_override(client, hw_submission_ai_graded):
    r = await client.patch(
        f"/api/v1/submissions/{hw_submission_ai_graded['id']}/grade",
        json={"accept_ai": False, "score": 6, "feedback": "Needs improvement"},
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "graded"
    assert data["grading"]["final"]["score"] == 6
    assert data["grading"]["final"]["feedback"] == "Needs improvement"
    assert data["grading"]["final"]["accepted_ai"] is False


# ---------------------------------------------------------------------------
# accept_ai=false without score → 422
# ---------------------------------------------------------------------------

async def test_grade_override_no_score(client, hw_submission_ai_graded):
    r = await client.patch(
        f"/api/v1/submissions/{hw_submission_ai_graded['id']}/grade",
        json={"accept_ai": False},
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# accept_ai=true without AI grading → 409
# ---------------------------------------------------------------------------

async def test_grade_accept_ai_no_ai_data(client, hw_submission_raw):
    r = await client.patch(
        f"/api/v1/submissions/{hw_submission_raw['id']}/grade",
        json={"accept_ai": True},
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Student cannot grade → 403
# ---------------------------------------------------------------------------

async def test_grade_student_forbidden(client, hw_submission_ai_graded):
    r = await client.patch(
        f"/api/v1/submissions/{hw_submission_ai_graded['id']}/grade",
        json={"accept_ai": True},
        headers=STUDENT_HEADERS,
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Other teacher (non-owner) cannot grade → 403
# ---------------------------------------------------------------------------

async def test_grade_non_owner_forbidden(client, hw_submission_ai_graded):
    r = await client.patch(
        f"/api/v1/submissions/{hw_submission_ai_graded['id']}/grade",
        json={"accept_ai": True},
        headers=OTHER_TEACHER_HEADERS,
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Test submission cannot be graded → 422
# ---------------------------------------------------------------------------

async def test_grade_test_submission_fails(client, assignment):
    from tests.conftest import QUESTION_PAYLOAD
    r_q = await client.post(
        f"/api/v1/assignments/{assignment['id']}/questions",
        json=QUESTION_PAYLOAD,
        headers=TEACHER_HEADERS,
    )
    q_id = r_q.json()["id"]
    r_sub = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        json={"answers": [{"question_id": q_id, "answer": "4"}]},
        headers=STUDENT_HEADERS,
    )
    assert r_sub.status_code == 201
    sub_id = r_sub.json()["id"]

    r = await client.patch(
        f"/api/v1/submissions/{sub_id}/grade",
        json={"accept_ai": False, "score": 5},
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# After grading: student sees final but not grading.ai
# ---------------------------------------------------------------------------

async def test_grade_student_sees_final_not_ai(client, hw_submission_ai_graded):
    await client.patch(
        f"/api/v1/submissions/{hw_submission_ai_graded['id']}/grade",
        json={"accept_ai": True},
        headers=TEACHER_HEADERS,
    )
    r = await client.get(
        f"/api/v1/submissions/{hw_submission_ai_graded['id']}",
        headers=STUDENT_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "graded"
    assert data["grading"]["final"]["score"] == FAKE_AI_GRADING["score"]
    assert data["grading"]["ai"] is None  # AI grading hidden from student
