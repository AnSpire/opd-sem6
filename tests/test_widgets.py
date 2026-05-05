import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

from tests.conftest import WIDGET_PAYLOAD


# ---------------------------------------------------------------------------
# POST /api/v1/widgets
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_widget_as_teacher(client, teacher_headers):
    r = await client.post("/api/v1/widgets", json=WIDGET_PAYLOAD, headers=teacher_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["id"] == WIDGET_PAYLOAD["id"]
    assert data["board_id"] == WIDGET_PAYLOAD["board_id"]
    assert data["creator_user_id"] == int(teacher_headers["x-user-id"])


@pytest.mark.asyncio
async def test_create_widget_as_student_forbidden(client, student_headers):
    r = await client.post("/api/v1/widgets", json=WIDGET_PAYLOAD, headers=student_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_widget_missing_headers_unprocessable(client):
    r = await client.post("/api/v1/widgets", json=WIDGET_PAYLOAD)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_widget_idempotent_by_board_and_creator(client, teacher_headers):
    """Same board_id + creator_user_id must return the same widget regardless of id."""
    r1 = await client.post("/api/v1/widgets", json=WIDGET_PAYLOAD, headers=teacher_headers)
    r2 = await client.post("/api/v1/widgets", json={"id": 999, "board_id": 10}, headers=teacher_headers)
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


# ---------------------------------------------------------------------------
# GET /api/v1/widgets/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_widget_exists(client, widget, teacher_headers):
    r = await client.get(f"/api/v1/widgets/{widget['id']}", headers=teacher_headers)
    assert r.status_code == 200
    assert r.json()["id"] == widget["id"]


@pytest.mark.asyncio
async def test_get_widget_not_found(client, teacher_headers):
    r = await client.get("/api/v1/widgets/999", headers=teacher_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_widget_visible_to_student(client, widget, student_headers):
    r = await client.get(f"/api/v1/widgets/{widget['id']}", headers=student_headers)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/v1/widgets/{id}/info
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_info_returns_widget(client, widget, teacher_headers):
    r = await client.post(f"/api/v1/widgets/{widget['id']}/info", headers=teacher_headers)
    assert r.status_code == 200
    assert r.json()["id"] == widget["id"]


@pytest.mark.asyncio
async def test_set_info_not_found(client, teacher_headers):
    r = await client.post("/api/v1/widgets/999/info", headers=teacher_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/widgets/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_widget_as_owner(client, widget, teacher_headers):
    r = await client.delete(f"/api/v1/widgets/{widget['id']}", headers=teacher_headers)
    assert r.status_code == 204
    r2 = await client.get(f"/api/v1/widgets/{widget['id']}", headers=teacher_headers)
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_delete_widget_as_non_owner_forbidden(client, widget, other_teacher_headers):
    r = await client.delete(f"/api/v1/widgets/{widget['id']}", headers=other_teacher_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_widget_as_student_forbidden(client, widget, student_headers):
    r = await client.delete(f"/api/v1/widgets/{widget['id']}", headers=student_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_widget_not_found(client, teacher_headers):
    r = await client.delete("/api/v1/widgets/999", headers=teacher_headers)
    assert r.status_code == 404
