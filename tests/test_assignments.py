import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

from tests.conftest import ASSIGNMENT_PAYLOAD


# ---------------------------------------------------------------------------
# POST /api/v1/widgets/{id}/assignments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_assignment_as_teacher(client, widget, teacher_headers):
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json=ASSIGNMENT_PAYLOAD,
        headers=teacher_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert "assignment" in data
    assert "config" in data
    assert data["assignment"]["title"] == ASSIGNMENT_PAYLOAD["title"]
    assert data["assignment"]["widget_id"] == widget["id"]
    assert data["config"]["assignments_count"] == 1
    assert len(data["config"]["preview"]) == 1


@pytest.mark.asyncio
async def test_create_assignment_as_student_forbidden(client, widget, student_headers):
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json=ASSIGNMENT_PAYLOAD,
        headers=student_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_assignment_non_owner_teacher_forbidden(client, widget, other_teacher_headers):
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json=ASSIGNMENT_PAYLOAD,
        headers=other_teacher_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_assignment_widget_not_found(client, teacher_headers):
    r = await client.post(
        "/api/v1/widgets/999/assignments",
        json=ASSIGNMENT_PAYLOAD,
        headers=teacher_headers,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/widgets/{id}/assignments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_assignments_empty(client, widget, teacher_headers):
    r = await client.get(f"/api/v1/widgets/{widget['id']}/assignments", headers=teacher_headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_assignments_returns_created(client, widget, assignment, teacher_headers):
    r = await client.get(f"/api/v1/widgets/{widget['id']}/assignments", headers=teacher_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == assignment["id"]


@pytest.mark.asyncio
async def test_list_assignments_visible_to_student(client, widget, assignment, student_headers):
    r = await client.get(f"/api/v1/widgets/{widget['id']}/assignments", headers=student_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1


# ---------------------------------------------------------------------------
# GET /api/v1/assignments/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_assignment(client, assignment, teacher_headers):
    r = await client.get(f"/api/v1/assignments/{assignment['id']}", headers=teacher_headers)
    assert r.status_code == 200
    assert r.json()["title"] == ASSIGNMENT_PAYLOAD["title"]


@pytest.mark.asyncio
async def test_get_assignment_not_found(client, teacher_headers):
    r = await client.get("/api/v1/assignments/999", headers=teacher_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_assignment_visible_to_student(client, assignment, student_headers):
    r = await client.get(f"/api/v1/assignments/{assignment['id']}", headers=student_headers)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /api/v1/assignments/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_assignment(client, assignment, teacher_headers):
    r = await client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"title": "Updated title", "max_score": 20},
        headers=teacher_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["assignment"]["title"] == "Updated title"
    assert data["assignment"]["max_score"] == 20
    assert "config" in data


@pytest.mark.asyncio
async def test_update_assignment_partial(client, assignment, teacher_headers):
    """PATCH is partial — unspecified fields must keep original values."""
    r = await client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"title": "Only title changed"},
        headers=teacher_headers,
    )
    assert r.status_code == 200
    data = r.json()["assignment"]
    assert data["title"] == "Only title changed"
    assert data["max_score"] == ASSIGNMENT_PAYLOAD["max_score"]


@pytest.mark.asyncio
async def test_update_assignment_config_updated(client, widget, teacher_headers):
    """Config preview title must reflect the updated title."""
    r_create = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json=ASSIGNMENT_PAYLOAD,
        headers=teacher_headers,
    )
    aid = r_create.json()["assignment"]["id"]
    r = await client.patch(
        f"/api/v1/assignments/{aid}",
        json={"title": "New title"},
        headers=teacher_headers,
    )
    preview_titles = [p["title"] for p in r.json()["config"]["preview"]]
    assert "New title" in preview_titles


@pytest.mark.asyncio
async def test_update_assignment_non_owner_forbidden(client, assignment, other_teacher_headers):
    r = await client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"title": "Hacked"},
        headers=other_teacher_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_assignment_student_forbidden(client, assignment, student_headers):
    r = await client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"title": "Hacked"},
        headers=student_headers,
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/v1/assignments/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_assignment(client, assignment, teacher_headers):
    r = await client.delete(
        f"/api/v1/assignments/{assignment['id']}", headers=teacher_headers
    )
    assert r.status_code == 200
    assert r.json()["config"]["assignments_count"] == 0


@pytest.mark.asyncio
async def test_delete_assignment_removes_from_list(client, widget, assignment, teacher_headers):
    await client.delete(f"/api/v1/assignments/{assignment['id']}", headers=teacher_headers)
    r = await client.get(f"/api/v1/widgets/{widget['id']}/assignments", headers=teacher_headers)
    assert r.json() == []


@pytest.mark.asyncio
async def test_delete_assignment_non_owner_forbidden(client, assignment, other_teacher_headers):
    r = await client.delete(
        f"/api/v1/assignments/{assignment['id']}", headers=other_teacher_headers
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_assignment_not_found(client, teacher_headers):
    r = await client.delete("/api/v1/assignments/999", headers=teacher_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# widget:updated / config invariants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_config_preview_max_3(client, widget, teacher_headers):
    """Preview must contain at most 3 assignments even when there are more."""
    for i in range(5):
        await client.post(
            f"/api/v1/widgets/{widget['id']}/assignments",
            json={**ASSIGNMENT_PAYLOAD, "title": f"A{i}"},
            headers=teacher_headers,
        )
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**ASSIGNMENT_PAYLOAD, "title": "Last"},
        headers=teacher_headers,
    )
    config = r.json()["config"]
    assert config["assignments_count"] == 6
    assert len(config["preview"]) == 3


@pytest.mark.asyncio
async def test_config_count_decrements_on_delete(client, widget, teacher_headers):
    r1 = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json=ASSIGNMENT_PAYLOAD,
        headers=teacher_headers,
    )
    r2 = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json={**ASSIGNMENT_PAYLOAD, "title": "Second"},
        headers=teacher_headers,
    )
    assert r2.json()["config"]["assignments_count"] == 2
    aid = r1.json()["assignment"]["id"]
    r3 = await client.delete(f"/api/v1/assignments/{aid}", headers=teacher_headers)
    assert r3.json()["config"]["assignments_count"] == 1
