from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio(loop_scope="session")

from tests.conftest import TEACHER_HEADERS, STUDENT_HEADERS

HW_ASSIGNMENT_PAYLOAD = {
    "type": "homework",
    "title": "Essay #1",
    "description": "Write an essay",
    "max_score": 20,
    "final_score_strategy": "last",
}

HW_DETAILS_PAYLOAD = {
    "prompt": "Explain recursion",
    "accepted_formats": ["text", "markdown", "image", "pdf"],
}

HW_DETAILS_RESTRICTED = {
    "prompt": "Explain recursion",
    "accepted_formats": ["pdf"],
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
# POST /assignments/{id}/submissions  — homework via multipart
# ---------------------------------------------------------------------------

async def test_submit_homework_text_only(client, hw_details, hw_assignment):
    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            data={"text": "My answer here"},
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 201
    data = r.json()
    assert data["type"] == "homework"
    assert data["status"] == "pending_ai"
    assert data["attempt_number"] == 1
    assert data["payload"]["text"] == "My answer here"
    assert data["payload"]["attachments"] == []
    assert data["grading"]["ai"] is None
    assert data["grading"]["final"] is None
    assert data["effective_score"] is None


async def test_submit_homework_with_pdf(client, hw_details, hw_assignment):
    pdf_content = b"%PDF-1.4 test content"
    with patch("app.services.storage.upload_object", new_callable=AsyncMock) as mock_upload:
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            data={"text": "See attachment"},
            files=[("files", ("report.pdf", pdf_content, "application/pdf"))],
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "pending_ai"
    assert len(data["payload"]["attachments"]) == 1
    att = data["payload"]["attachments"][0]
    assert att["kind"] == "pdf"
    assert att["filename"] == "report.pdf"
    assert att["mime"] == "application/pdf"
    assert att["size"] == len(pdf_content)
    assert mock_upload.call_count == 1


async def test_submit_homework_multiple_files(client, hw_details, hw_assignment):
    files = [
        ("files", (f"img{i}.png", b"fakepng", "image/png"))
        for i in range(3)
    ]
    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            files=files,
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 201
    assert len(r.json()["payload"]["attachments"]) == 3


async def test_submit_homework_too_many_files(client, hw_details, hw_assignment):
    files = [
        ("files", (f"img{i}.png", b"fakepng", "image/png"))
        for i in range(6)
    ]
    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            files=files,
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 422


async def test_submit_homework_file_too_large(client, hw_details, hw_assignment):
    big = b"x" * (10 * 1024 * 1024 + 1)
    with patch("app.services.storage.upload_object", new_callable=AsyncMock), \
         patch("app.services.storage.delete_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            files=[("files", ("big.pdf", big, "application/pdf"))],
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 422


async def test_submit_homework_disallowed_format(client, widget, hw_assignment):
    r = await client.put(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        json=HW_DETAILS_RESTRICTED,
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 200

    with patch("app.services.storage.upload_object", new_callable=AsyncMock), \
         patch("app.services.storage.delete_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            files=[("files", ("photo.png", b"fakepng", "image/png"))],
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 422


async def test_submit_homework_teacher_forbidden(client, hw_details, hw_assignment):
    r = await client.post(
        f"/api/v1/assignments/{hw_assignment['id']}/submissions",
        data={"text": "Teacher should not submit"},
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 403


async def test_submit_homework_deadline_late_not_allowed(client, widget):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**HW_ASSIGNMENT_PAYLOAD, "deadline": past, "allow_late_submissions": False},
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 201
    asgn = r.json()["assignment"]

    await client.put(
        f"/api/v1/assignments/{asgn['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )

    r = await client.post(
        f"/api/v1/assignments/{asgn['id']}/submissions",
        data={"text": "Late answer"},
        headers=STUDENT_HEADERS,
    )
    assert r.status_code == 409


async def test_submit_homework_deadline_late_allowed(client, widget):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**HW_ASSIGNMENT_PAYLOAD, "deadline": past, "allow_late_submissions": True},
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 201
    asgn = r.json()["assignment"]

    await client.put(
        f"/api/v1/assignments/{asgn['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )

    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{asgn['id']}/submissions",
            data={"text": "Late but allowed"},
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 201
    assert r.json()["is_late"] is True


async def test_submit_homework_max_attempts(client, widget):
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**HW_ASSIGNMENT_PAYLOAD, "max_attempts": 1},
        headers=TEACHER_HEADERS,
    )
    assert r.status_code == 201
    asgn = r.json()["assignment"]

    await client.put(
        f"/api/v1/assignments/{asgn['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )

    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r1 = await client.post(
            f"/api/v1/assignments/{asgn['id']}/submissions",
            data={"text": "First"},
            headers=STUDENT_HEADERS,
        )
    assert r1.status_code == 201

    r2 = await client.post(
        f"/api/v1/assignments/{asgn['id']}/submissions",
        data={"text": "Second — should fail"},
        headers=STUDENT_HEADERS,
    )
    assert r2.status_code == 409


async def test_submit_multipart_to_test_assignment_fails(client, assignment):
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        data={"text": "wrong type"},
        headers=STUDENT_HEADERS,
    )
    assert r.status_code == 422


async def test_submit_homework_attempt_increments(client, hw_details, hw_assignment):
    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r1 = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            data={"text": "First attempt"},
            headers=STUDENT_HEADERS,
        )
        r2 = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            data={"text": "Second attempt"},
            headers=STUDENT_HEADERS,
        )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["attempt_number"] == 1
    assert r2.json()["attempt_number"] == 2


async def test_submit_homework_enqueues_grade_job(client, hw_details, hw_assignment):
    mock_pool = AsyncMock()
    with patch("app.db.arq_pool.pool", mock_pool), \
         patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            data={"text": "My answer"},
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 201
    submission_id = r.json()["id"]
    mock_pool.enqueue_job.assert_awaited_once_with("grade_submission", submission_id)


async def test_student_submission_response_hides_ai_grading(client, hw_details, hw_assignment):
    """Student's submission response must never expose grading.ai."""
    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            data={"text": "My answer"},
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 201
    assert r.json()["grading"]["ai"] is None


async def test_student_get_submission_hides_ai_grading(client, hw_details, hw_assignment):
    """Student's GET /submissions/{id} must not expose grading.ai even after AI processes it."""
    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            data={"text": "My answer"},
            headers=STUDENT_HEADERS,
        )
    submission_id = r.json()["id"]

    # Simulate worker setting AI grading
    from app.repositories.submissions import update_grading
    from app.db.mongo import get_db
    await update_grading(get_db(), submission_id, "pending_teacher", {
        "score": 9, "max_score": 20, "feedback": "AI says great", "rubric_breakdown": [],
    })

    r = await client.get(
        f"/api/v1/submissions/{submission_id}",
        headers=STUDENT_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["grading"]["ai"] is None
    assert r.json()["status"] == "pending_teacher"
