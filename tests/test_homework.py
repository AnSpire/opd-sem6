import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio(loop_scope="session")

from tests.conftest import TEACHER_HEADERS, STUDENT_HEADERS, OTHER_TEACHER_HEADERS

HW_ASSIGNMENT_PAYLOAD = {
    "type": "homework",
    "title": "Essay #1",
    "description": "Write an essay",
    "max_score": 20,
    "final_score_strategy": "last",
}

HW_DETAILS_PAYLOAD = {
    "prompt": "Explain the concept of recursion",
    "reference_answer": "A function that calls itself",
    "grading_criteria": "Clarity, correctness",
    "accepted_formats": ["text", "markdown"],
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
async def hw_details(client, hw_assignment):
    r = await client.put(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 200
    return r.json()


# ---------------------------------------------------------------------------
# PUT /assignments/{id}/homework
# ---------------------------------------------------------------------------

async def test_upsert_homework_creates(client, hw_assignment):
    r = await client.put(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignment_id"] == hw_assignment["id"]
    assert data["prompt"] == HW_DETAILS_PAYLOAD["prompt"]
    assert data["reference_answer"] == HW_DETAILS_PAYLOAD["reference_answer"]
    assert data["grading_criteria"] == HW_DETAILS_PAYLOAD["grading_criteria"]
    assert data["accepted_formats"] == HW_DETAILS_PAYLOAD["accepted_formats"]


async def test_upsert_homework_updates(client, hw_details, hw_assignment):
    updated = {**HW_DETAILS_PAYLOAD, "prompt": "New prompt", "accepted_formats": ["pdf"]}
    r = await client.put(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        json=updated,
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["prompt"] == "New prompt"
    assert data["accepted_formats"] == ["pdf"]


async def test_upsert_homework_student_forbidden(client, hw_assignment):
    r = await client.put(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=STUDENT_HEADERS,
    )
    assert r.status_code == 403


async def test_upsert_homework_other_teacher_forbidden(client, hw_assignment):
    r = await client.put(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=OTHER_TEACHER_HEADERS,
    )
    assert r.status_code == 403


async def test_upsert_homework_wrong_type(client, assignment):
    r = await client.put(
        f"/api/v1/assignments/{assignment['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 422


async def test_upsert_homework_not_found(client):
    r = await client.put(
        "/api/v1/assignments/99999/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /assignments/{id}/homework
# ---------------------------------------------------------------------------

async def test_get_homework_teacher(client, hw_details, hw_assignment):
    r = await client.get(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["prompt"] == HW_DETAILS_PAYLOAD["prompt"]


async def test_get_homework_student(client, hw_details, hw_assignment):
    r = await client.get(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        headers=STUDENT_HEADERS,
    )
    assert r.status_code == 200


async def test_get_homework_not_found(client, hw_assignment):
    r = await client.get(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 404
