from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio(loop_scope="session")

from tests.conftest import TEACHER_HEADERS, STUDENT_HEADERS, OTHER_TEACHER_HEADERS

HW_ASSIGNMENT_PAYLOAD = {
    "type": "homework",
    "title": "Attachment Test Assignment",
    "max_score": 10,
    "final_score_strategy": "last",
}

HW_DETAILS_PAYLOAD = {
    "prompt": "Submit your work",
    "accepted_formats": ["pdf", "image"],
}

PRESIGNED_URL = "http://minio:9000/bucket/key?sig=fake"


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
async def submission_with_file(client, hw_assignment):
    await client.put(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )
    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            files=[("files", ("doc.pdf", b"%PDF-fake", "application/pdf"))],
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# GET /attachments/{submission_id}/{attachment_index}
# ---------------------------------------------------------------------------

async def test_student_gets_own_attachment(client, submission_with_file):
    sid = submission_with_file["id"]
    with patch("app.services.storage.presigned_get_url", new_callable=AsyncMock, return_value=PRESIGNED_URL):
        r = await client.get(f"/api/v1/attachments/{sid}/0", headers=STUDENT_HEADERS)
    assert r.status_code == 200
    assert r.json()["url"] == PRESIGNED_URL


async def test_teacher_owner_gets_attachment(client, submission_with_file):
    sid = submission_with_file["id"]
    with patch("app.services.storage.presigned_get_url", new_callable=AsyncMock, return_value=PRESIGNED_URL):
        r = await client.get(f"/api/v1/attachments/{sid}/0", headers=TEACHER_HEADERS)
    assert r.status_code == 200
    assert r.json()["url"] == PRESIGNED_URL


async def test_other_teacher_forbidden(client, submission_with_file):
    sid = submission_with_file["id"]
    with patch("app.services.storage.presigned_get_url", new_callable=AsyncMock, return_value=PRESIGNED_URL):
        r = await client.get(f"/api/v1/attachments/{sid}/0", headers=OTHER_TEACHER_HEADERS)
    assert r.status_code == 403


async def test_other_student_forbidden(client, submission_with_file):
    sid = submission_with_file["id"]
    other_student = {"x-user-id": "999", "x-user-role": "student", "x-board-id": "10", "x-widget-id": "1"}
    with patch("app.services.storage.presigned_get_url", new_callable=AsyncMock, return_value=PRESIGNED_URL):
        r = await client.get(f"/api/v1/attachments/{sid}/0", headers=other_student)
    assert r.status_code == 403


async def test_attachment_index_out_of_range(client, submission_with_file):
    sid = submission_with_file["id"]
    with patch("app.services.storage.presigned_get_url", new_callable=AsyncMock, return_value=PRESIGNED_URL):
        r = await client.get(f"/api/v1/attachments/{sid}/5", headers=STUDENT_HEADERS)
    assert r.status_code == 404


async def test_attachment_no_files_submission(client, hw_assignment):
    await client.put(
        f"/api/v1/assignments/{hw_assignment['id']}/homework",
        json=HW_DETAILS_PAYLOAD,
        headers=TEACHER_HEADERS,
    )
    with patch("app.services.storage.upload_object", new_callable=AsyncMock):
        r = await client.post(
            f"/api/v1/assignments/{hw_assignment['id']}/submissions",
            data={"text": "no files"},
            headers=STUDENT_HEADERS,
        )
    assert r.status_code == 201
    sid = r.json()["id"]

    r = await client.get(f"/api/v1/attachments/{sid}/0", headers=STUDENT_HEADERS)
    assert r.status_code == 404


async def test_submission_not_found(client):
    r = await client.get(
        "/api/v1/attachments/000000000000000000000000/0",
        headers=STUDENT_HEADERS,
    )
    assert r.status_code == 404
