import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

from tests.conftest import QUESTION_PAYLOAD


# ---------------------------------------------------------------------------
# POST /api/v1/assignments/{id}/questions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_question_as_teacher(client, assignment, teacher_headers):
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/questions",
        json=QUESTION_PAYLOAD,
        headers=teacher_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["text"] == QUESTION_PAYLOAD["text"]
    assert data["assignment_id"] == assignment["id"]
    assert data["correct_answer"] == QUESTION_PAYLOAD["correct_answer"]


@pytest.mark.asyncio
async def test_create_question_as_student_forbidden(client, assignment, student_headers):
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/questions",
        json=QUESTION_PAYLOAD,
        headers=student_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_question_non_owner_forbidden(client, assignment, other_teacher_headers):
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/questions",
        json=QUESTION_PAYLOAD,
        headers=other_teacher_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_question_assignment_not_found(client, teacher_headers):
    r = await client.post(
        "/api/v1/assignments/999/questions",
        json=QUESTION_PAYLOAD,
        headers=teacher_headers,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/assignments/{id}/questions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_questions_empty(client, assignment, teacher_headers):
    r = await client.get(
        f"/api/v1/assignments/{assignment['id']}/questions",
        headers=teacher_headers,
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_questions_teacher_sees_correct_answer(client, assignment, question, teacher_headers):
    r = await client.get(
        f"/api/v1/assignments/{assignment['id']}/questions",
        headers=teacher_headers,
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["correct_answer"] == QUESTION_PAYLOAD["correct_answer"]


@pytest.mark.asyncio
async def test_list_questions_student_correct_answer_hidden(client, assignment, question, student_headers):
    r = await client.get(
        f"/api/v1/assignments/{assignment['id']}/questions",
        headers=student_headers,
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["correct_answer"] is None


@pytest.mark.asyncio
async def test_list_questions_ordered_by_order(client, assignment, teacher_headers):
    for i in [3, 1, 2]:
        await client.post(
            f"/api/v1/assignments/{assignment['id']}/questions",
            json={**QUESTION_PAYLOAD, "order": i, "text": f"Q{i}"},
            headers=teacher_headers,
        )
    r = await client.get(
        f"/api/v1/assignments/{assignment['id']}/questions",
        headers=teacher_headers,
    )
    orders = [q["order"] for q in r.json()]
    assert orders == sorted(orders)


# ---------------------------------------------------------------------------
# PATCH /api/v1/questions/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_question(client, question, teacher_headers):
    r = await client.patch(
        f"/api/v1/questions/{question['id']}",
        json={"text": "Updated text", "points": 10},
        headers=teacher_headers,
    )
    assert r.status_code == 200
    assert r.json()["text"] == "Updated text"
    assert r.json()["points"] == 10


@pytest.mark.asyncio
async def test_update_question_partial(client, question, teacher_headers):
    r = await client.patch(
        f"/api/v1/questions/{question['id']}",
        json={"text": "Only text changed"},
        headers=teacher_headers,
    )
    assert r.status_code == 200
    assert r.json()["points"] == QUESTION_PAYLOAD["points"]


@pytest.mark.asyncio
async def test_update_question_non_owner_forbidden(client, question, other_teacher_headers):
    r = await client.patch(
        f"/api/v1/questions/{question['id']}",
        json={"text": "Hack"},
        headers=other_teacher_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_question_student_forbidden(client, question, student_headers):
    r = await client.patch(
        f"/api/v1/questions/{question['id']}",
        json={"text": "Hack"},
        headers=student_headers,
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/v1/questions/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_question(client, question, teacher_headers):
    r = await client.delete(
        f"/api/v1/questions/{question['id']}",
        headers=teacher_headers,
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_delete_question_removes_from_list(client, assignment, question, teacher_headers):
    await client.delete(f"/api/v1/questions/{question['id']}", headers=teacher_headers)
    r = await client.get(
        f"/api/v1/assignments/{assignment['id']}/questions",
        headers=teacher_headers,
    )
    assert r.json() == []


@pytest.mark.asyncio
async def test_delete_question_non_owner_forbidden(client, question, other_teacher_headers):
    r = await client.delete(
        f"/api/v1/questions/{question['id']}",
        headers=other_teacher_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_question_not_found(client, teacher_headers):
    r = await client.delete("/api/v1/questions/999", headers=teacher_headers)
    assert r.status_code == 404
