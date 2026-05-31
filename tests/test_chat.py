"""Tests for 1-on-1 chat: profiles, conversations, messages."""
import pytest

TEACHER_H = {"x-user-id": "1", "x-user-role": "teacher", "x-board-id": "10"}
STUDENT_H = {"x-user-id": "2", "x-user-role": "student", "x-board-id": "10"}
OTHER_H = {"x-user-id": "3", "x-user-role": "student", "x-board-id": "10"}
OUTSIDER_H = {"x-user-id": "99", "x-user-role": "student", "x-board-id": "20"}


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_profile_create(client):
    r = await client.put(
        "/api/v1/users/me/profile",
        json={"display_name": "Alice"},
        headers=TEACHER_H,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["display_name"] == "Alice"
    assert data["user_id"] == 1


@pytest.mark.asyncio
async def test_upsert_profile_update(client):
    await client.put("/api/v1/users/me/profile", json={"display_name": "Alice"}, headers=TEACHER_H)
    r = await client.put(
        "/api/v1/users/me/profile",
        json={"display_name": "Alice Updated", "avatar_url": "https://example.com/avatar.png"},
        headers=TEACHER_H,
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Alice Updated"


@pytest.mark.asyncio
async def test_get_profile_found(client):
    await client.put("/api/v1/users/me/profile", json={"display_name": "Alice"}, headers=TEACHER_H)
    r = await client.get("/api/v1/users/1/profile", headers=STUDENT_H)
    assert r.status_code == 200
    assert r.json()["user_id"] == 1


@pytest.mark.asyncio
async def test_get_profile_not_found(client):
    r = await client.get("/api/v1/users/999/profile", headers=TEACHER_H)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_conversation(client):
    r = await client.post(
        "/api/v1/conversations",
        json={"other_user_id": 2, "board_id": 10},
        headers=TEACHER_H,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["board_id"] == 10
    assert set([data["user1_id"], data["user2_id"]]) == {1, 2}


@pytest.mark.asyncio
async def test_create_conversation_idempotent(client):
    r1 = await client.post(
        "/api/v1/conversations",
        json={"other_user_id": 2, "board_id": 10},
        headers=TEACHER_H,
    )
    r2 = await client.post(
        "/api/v1/conversations",
        json={"other_user_id": 2, "board_id": 10},
        headers=TEACHER_H,
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


@pytest.mark.asyncio
async def test_create_conversation_with_self_returns_400(client):
    r = await client.post(
        "/api/v1/conversations",
        json={"other_user_id": 1, "board_id": 10},
        headers=TEACHER_H,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_conversations_empty(client):
    r = await client.get("/api/v1/conversations", headers=TEACHER_H)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_conversations(client):
    await client.post(
        "/api/v1/conversations",
        json={"other_user_id": 2, "board_id": 10},
        headers=TEACHER_H,
    )
    r = await client.get("/api/v1/conversations", headers=TEACHER_H)
    assert r.status_code == 200
    assert len(r.json()) == 1


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


async def _make_conv(client):
    r = await client.post(
        "/api/v1/conversations",
        json={"other_user_id": 2, "board_id": 10},
        headers=TEACHER_H,
    )
    return r.json()["id"]


@pytest.mark.asyncio
async def test_send_message(client):
    conv_id = await _make_conv(client)
    r = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "Hello!"},
        headers=TEACHER_H,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["text"] == "Hello!"
    assert data["sender_id"] == 1
    assert data["read_at"] is None
    assert data["deleted_at"] is None


@pytest.mark.asyncio
async def test_send_message_not_participant(client):
    conv_id = await _make_conv(client)
    r = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "Intruder!"},
        headers=OUTSIDER_H,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_messages_history(client):
    conv_id = await _make_conv(client)
    for i in range(3):
        await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"text": f"msg {i}"},
            headers=TEACHER_H,
        )
    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=TEACHER_H)
    assert r.status_code == 200
    assert len(r.json()) == 3


@pytest.mark.asyncio
async def test_get_messages_cursor_pagination(client):
    conv_id = await _make_conv(client)
    ids = []
    for i in range(5):
        r = await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"text": f"msg {i}"},
            headers=TEACHER_H,
        )
        ids.append(r.json()["id"])

    # Get messages before the 4th (index 3) — should return 3 earlier ones
    r = await client.get(
        f"/api/v1/conversations/{conv_id}/messages",
        params={"before_id": ids[3], "limit": 10},
        headers=TEACHER_H,
    )
    assert r.status_code == 200
    returned_ids = [m["id"] for m in r.json()]
    assert ids[3] not in returned_ids
    assert len(returned_ids) == 3


@pytest.mark.asyncio
async def test_mark_read(client):
    conv_id = await _make_conv(client)
    r = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "read me"},
        headers=TEACHER_H,
    )
    msg_id = r.json()["id"]

    # Student marks read
    r = await client.patch(
        f"/api/v1/conversations/{conv_id}/read",
        json={"message_id": msg_id},
        headers=STUDENT_H,
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_delete_own_message(client):
    conv_id = await _make_conv(client)
    r = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "delete me"},
        headers=TEACHER_H,
    )
    msg_id = r.json()["id"]

    r = await client.delete(
        f"/api/v1/conversations/{conv_id}/messages/{msg_id}",
        headers=TEACHER_H,
    )
    assert r.status_code == 204

    # Deleted message no longer appears in history
    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=TEACHER_H)
    assert all(m["id"] != msg_id for m in r.json())


@pytest.mark.asyncio
async def test_delete_other_user_message_forbidden(client):
    conv_id = await _make_conv(client)
    r = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "not yours"},
        headers=TEACHER_H,
    )
    msg_id = r.json()["id"]

    # Student tries to delete teacher's message
    r = await client.delete(
        f"/api/v1/conversations/{conv_id}/messages/{msg_id}",
        headers=STUDENT_H,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_conversation_last_message_in_list(client):
    conv_id = await _make_conv(client)
    await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "last one"},
        headers=TEACHER_H,
    )
    r = await client.get("/api/v1/conversations", headers=TEACHER_H)
    convs = r.json()
    assert len(convs) == 1
    assert convs[0]["last_message"]["text"] == "last one"


@pytest.mark.asyncio
async def test_unread_count(client):
    conv_id = await _make_conv(client)
    # Teacher sends 2 messages; student hasn't read them
    for _ in range(2):
        await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"text": "ping"},
            headers=TEACHER_H,
        )
    r = await client.get("/api/v1/conversations", headers=STUDENT_H)
    convs = r.json()
    assert convs[0]["unread_count"] == 2
