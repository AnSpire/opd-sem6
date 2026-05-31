import json
from datetime import datetime, timezone

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories
from app.models.conversation import Conversation
from app.models.user_profile import UserProfile
from app.repositories import chat as chat_repo
from app.schemas.chat import ConversationOut, MessageOut, ProfileOut


async def upsert_profile(session: AsyncSession, user_id: int, display_name: str, avatar_url: str | None) -> UserProfile:
    stmt = pg_insert(UserProfile).values(
        user_id=user_id,
        display_name=display_name,
        avatar_url=avatar_url,
    ).on_conflict_do_update(
        index_elements=["user_id"],
        set_={"display_name": display_name, "avatar_url": avatar_url},
    ).returning(UserProfile)
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


async def get_profile_or_404(session: AsyncSession, user_id: int) -> UserProfile:
    stmt = select(UserProfile).where(UserProfile.user_id == user_id)
    profile = (await session.execute(stmt)).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    return profile


def _normalize(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


async def upsert_conversation(
    session: AsyncSession,
    board_id: int,
    user_id: int,
    other_user_id: int,
) -> Conversation:
    if user_id == other_user_id:
        raise HTTPException(status_code=400, detail="Cannot start a conversation with yourself")
    u1, u2 = _normalize(user_id, other_user_id)
    stmt = select(Conversation).where(
        Conversation.board_id == board_id,
        Conversation.user1_id == u1,
        Conversation.user2_id == u2,
    )
    conv = (await session.execute(stmt)).scalar_one_or_none()
    if conv:
        return conv
    conv = Conversation(board_id=board_id, user1_id=u1, user2_id=u2)
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def get_conversation_or_404(session: AsyncSession, conv_id: int) -> Conversation:
    stmt = select(Conversation).where(Conversation.id == conv_id)
    conv = (await session.execute(stmt)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def require_participant(conv: Conversation, user_id: int) -> None:
    if conv.user1_id != user_id and conv.user2_id != user_id:
        raise HTTPException(status_code=403, detail="Not a participant of this conversation")


async def list_conversations(
    session: AsyncSession,
    db: AsyncIOMotorDatabase,
    user_id: int,
) -> list[ConversationOut]:
    stmt = select(Conversation).where(
        (Conversation.user1_id == user_id) | (Conversation.user2_id == user_id)
    ).order_by(Conversation.last_msg_at.desc().nullslast())
    convs = (await session.execute(stmt)).scalars().all()

    result = []
    for conv in convs:
        last_msg = await chat_repo.get_last_message(db, conv.id)
        unread = await chat_repo.count_unread(db, conv.id, user_id)
        out = ConversationOut.model_validate(conv)
        out.last_message = last_msg
        out.unread_count = unread
        result.append(out)
    return result


async def send_message(
    session: AsyncSession,
    db: AsyncIOMotorDatabase,
    redis,
    conv: Conversation,
    sender_id: int,
    text: str,
) -> MessageOut:
    now = datetime.now(timezone.utc)
    doc = {
        "conversation_id": conv.id,
        "sender_id": sender_id,
        "text": text,
        "created_at": now,
        "read_at": None,
        "deleted_at": None,
    }
    inserted = await chat_repo.insert_message(db, doc)

    await session.execute(
        update(Conversation)
        .where(Conversation.id == conv.id)
        .values(last_msg_at=now)
    )
    await session.commit()

    msg_out = chat_repo._msg_to_out(inserted)

    if redis is not None:
        recipient_id = conv.user2_id if sender_id == conv.user1_id else conv.user1_id
        payload = json.dumps({
            "conversation_id": conv.id,
            "id": msg_out.id,
            "sender_id": sender_id,
            "text": text,
            "created_at": now.isoformat(),
        })
        await redis.publish(f"chat:user:{recipient_id}", payload)

    return msg_out
