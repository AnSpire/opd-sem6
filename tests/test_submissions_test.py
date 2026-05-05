from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

from tests.conftest import ASSIGNMENT_PAYLOAD, QUESTION_PAYLOAD

ANSWER_CORRECT = [{"question_id": None, "answer": "4"}]   # question_id filled in fixtures
ANSWER_WRONG = [{"question_id": None, "answer": "3"}]


def _answers(question_id: int, answer) -> list[dict]:
    return [{"question_id": question_id, "answer": answer}]


# ---------------------------------------------------------------------------
# POST /api/v1/assignments/{id}/submissions — basic grading
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_test_correct_answer(client, assignment, question, student_headers):
    body = {"answers": _answers(question["id"], "4")}
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        json=body,
        headers=student_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "auto_graded"
    assert data["attempt_number"] == 1
    assert data["is_late"] is False
    graded = data["payload"]["answers"][0]
    assert graded["is_correct"] is True
    assert graded["points_awarded"] == QUESTION_PAYLOAD["points"]
    assert data["grading"]["final"]["score"] == QUESTION_PAYLOAD["points"]
    assert data["effective_score"] == QUESTION_PAYLOAD["points"]


@pytest.mark.asyncio
async def test_submit_test_wrong_answer(client, assignment, question, student_headers):
    body = {"answers": _answers(question["id"], "3")}
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        json=body,
        headers=student_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["grading"]["final"]["score"] == 0
    assert data["payload"]["answers"][0]["is_correct"] is False


@pytest.mark.asyncio
async def test_submit_test_as_teacher_forbidden(client, assignment, question, teacher_headers):
    body = {"answers": _answers(question["id"], "4")}
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        json=body,
        headers=teacher_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_submit_test_assignment_not_found(client, student_headers):
    r = await client.post(
        "/api/v1/assignments/999/submissions",
        json={"answers": []},
        headers=student_headers,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Deadline enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_late_allowed(client, widget, question, student_headers, teacher_headers):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**ASSIGNMENT_PAYLOAD, "deadline": past, "allow_late_submissions": True},
        headers=teacher_headers,
    )
    aid = r.json()["assignment"]["id"]
    # create a question for this assignment
    rq = await client.post(
        f"/api/v1/assignments/{aid}/questions",
        json=QUESTION_PAYLOAD,
        headers=teacher_headers,
    )
    qid = rq.json()["id"]
    r2 = await client.post(
        f"/api/v1/assignments/{aid}/submissions",
        json={"answers": _answers(qid, "4")},
        headers=student_headers,
    )
    assert r2.status_code == 201
    assert r2.json()["is_late"] is True


@pytest.mark.asyncio
async def test_submit_late_not_allowed(client, widget, teacher_headers, student_headers):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**ASSIGNMENT_PAYLOAD, "deadline": past, "allow_late_submissions": False},
        headers=teacher_headers,
    )
    aid = r.json()["assignment"]["id"]
    r2 = await client.post(
        f"/api/v1/assignments/{aid}/submissions",
        json={"answers": []},
        headers=student_headers,
    )
    assert r2.status_code == 409


# ---------------------------------------------------------------------------
# Max attempts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_max_attempts_exceeded(client, widget, question, student_headers, teacher_headers):
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**ASSIGNMENT_PAYLOAD, "max_attempts": 1},
        headers=teacher_headers,
    )
    aid = r.json()["assignment"]["id"]
    rq = await client.post(
        f"/api/v1/assignments/{aid}/questions",
        json=QUESTION_PAYLOAD,
        headers=teacher_headers,
    )
    qid = rq.json()["id"]
    body = {"answers": _answers(qid, "4")}
    r1 = await client.post(f"/api/v1/assignments/{aid}/submissions", json=body, headers=student_headers)
    assert r1.status_code == 201
    r2 = await client.post(f"/api/v1/assignments/{aid}/submissions", json=body, headers=student_headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_attempt_number_increments(client, assignment, question, student_headers):
    body = {"answers": _answers(question["id"], "4")}
    r1 = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        json=body,
        headers=student_headers,
    )
    r2 = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        json=body,
        headers=student_headers,
    )
    assert r1.json()["attempt_number"] == 1
    assert r2.json()["attempt_number"] == 2


# ---------------------------------------------------------------------------
# final_score_strategy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_effective_score_strategy_best(client, widget, teacher_headers, student_headers):
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**ASSIGNMENT_PAYLOAD, "final_score_strategy": "best"},
        headers=teacher_headers,
    )
    aid = r.json()["assignment"]["id"]
    rq = await client.post(
        f"/api/v1/assignments/{aid}/questions",
        json=QUESTION_PAYLOAD,
        headers=teacher_headers,
    )
    qid = rq.json()["id"]
    await client.post(f"/api/v1/assignments/{aid}/submissions",
                      json={"answers": _answers(qid, "4")}, headers=student_headers)  # score=5
    r2 = await client.post(f"/api/v1/assignments/{aid}/submissions",
                           json={"answers": _answers(qid, "3")}, headers=student_headers)  # score=0
    assert r2.json()["effective_score"] == 5  # best


@pytest.mark.asyncio
async def test_effective_score_strategy_last(client, widget, teacher_headers, student_headers):
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**ASSIGNMENT_PAYLOAD, "final_score_strategy": "last"},
        headers=teacher_headers,
    )
    aid = r.json()["assignment"]["id"]
    rq = await client.post(
        f"/api/v1/assignments/{aid}/questions",
        json=QUESTION_PAYLOAD,
        headers=teacher_headers,
    )
    qid = rq.json()["id"]
    await client.post(f"/api/v1/assignments/{aid}/submissions",
                      json={"answers": _answers(qid, "4")}, headers=student_headers)  # score=5
    r2 = await client.post(f"/api/v1/assignments/{aid}/submissions",
                           json={"answers": _answers(qid, "3")}, headers=student_headers)  # score=0
    assert r2.json()["effective_score"] == 0  # last


@pytest.mark.asyncio
async def test_effective_score_strategy_average(client, widget, teacher_headers, student_headers):
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**ASSIGNMENT_PAYLOAD, "final_score_strategy": "average"},
        headers=teacher_headers,
    )
    aid = r.json()["assignment"]["id"]
    rq = await client.post(
        f"/api/v1/assignments/{aid}/questions",
        json=QUESTION_PAYLOAD,
        headers=teacher_headers,
    )
    qid = rq.json()["id"]
    await client.post(f"/api/v1/assignments/{aid}/submissions",
                      json={"answers": _answers(qid, "4")}, headers=student_headers)  # score=5
    r2 = await client.post(f"/api/v1/assignments/{aid}/submissions",
                           json={"answers": _answers(qid, "4")}, headers=student_headers)  # score=5
    assert r2.json()["effective_score"] == 5  # average of (5,5)=5


# ---------------------------------------------------------------------------
# GET /api/v1/assignments/{id}/submissions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_submissions_teacher_sees_all(client, assignment, question, teacher_headers, student_headers):
    body = {"answers": _answers(question["id"], "4")}
    await client.post(f"/api/v1/assignments/{assignment['id']}/submissions", json=body, headers=student_headers)
    r = await client.get(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        headers=teacher_headers,
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_list_submissions_student_sees_only_own(client, widget, question, teacher_headers, student_headers):
    # submission by student (user_id=2), assignment from fixture belongs to widget of teacher (user_id=1)
    assignment_id = question["assignment_id"]
    body = {"answers": _answers(question["id"], "4")}
    await client.post(f"/api/v1/assignments/{assignment_id}/submissions", json=body, headers=student_headers)

    # student headers has user_id=2, sees only own
    r = await client.get(
        f"/api/v1/assignments/{assignment_id}/submissions",
        headers=student_headers,
    )
    assert r.status_code == 200
    for sub in r.json():
        assert sub["student_user_id"] == 2


# ---------------------------------------------------------------------------
# GET /api/v1/submissions/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_submission_by_id_as_teacher(client, assignment, question, teacher_headers, student_headers):
    body = {"answers": _answers(question["id"], "4")}
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        json=body,
        headers=student_headers,
    )
    sub_id = r.json()["id"]
    r2 = await client.get(f"/api/v1/submissions/{sub_id}", headers=teacher_headers)
    assert r2.status_code == 200
    assert r2.json()["id"] == sub_id


@pytest.mark.asyncio
async def test_get_submission_by_id_as_owner_student(client, assignment, question, student_headers):
    body = {"answers": _answers(question["id"], "4")}
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        json=body,
        headers=student_headers,
    )
    sub_id = r.json()["id"]
    r2 = await client.get(f"/api/v1/submissions/{sub_id}", headers=student_headers)
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_get_submission_by_id_forbidden_for_other_student(
    client, assignment, question, student_headers
):
    body = {"answers": _answers(question["id"], "4")}
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        json=body,
        headers=student_headers,
    )
    sub_id = r.json()["id"]
    other_student = {"x-user-id": "999", "x-user-role": "student", "x-board-id": "10", "x-widget-id": "1"}
    r2 = await client.get(f"/api/v1/submissions/{sub_id}", headers=other_student)
    assert r2.status_code == 403
