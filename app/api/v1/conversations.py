from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import redis_pub
from app.db.mongo import get_db
from app.db.postgres import get_session
from app.deps import UserContext, get_current_user
from app.repositories import chat as chat_repo
from app.schemas.chat import (
    ConversationCreate,
    ConversationOut,
    MessageCreate,
    MessageOut,
    ReadBody,
)
from app.services import chat as chat_service

router = APIRouter(prefix="/conversations", tags=["chat"])


@router.post(
    "",
    response_model=ConversationOut,
    status_code=201,
    summary="Find-or-create 1-on-1 conversation",
)
async def create_conversation(
    body: ConversationCreate,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    conv = await chat_service.upsert_conversation(session, body.board_id, user.user_id, body.other_user_id)
    last_msg = await chat_repo.get_last_message(db, conv.id)
    unread = await chat_repo.count_unread(db, conv.id, user.user_id)
    out = ConversationOut.model_validate(conv)
    out.last_message = last_msg
    out.unread_count = unread
    return out


@router.get("", response_model=list[ConversationOut], summary="List my conversations")
async def list_my_conversations(
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await chat_service.list_conversations(session, db, user.user_id)


@router.get(
    "/{conv_id}/messages",
    response_model=list[MessageOut],
    summary="Get message history (cursor pagination)",
)
async def get_messages(
    conv_id: int,
    before_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    conv = await chat_service.get_conversation_or_404(session, conv_id)
    chat_service.require_participant(conv, user.user_id)
    return await chat_repo.list_messages(db, conv_id, before_id=before_id, limit=limit)


@router.post(
    "/{conv_id}/messages",
    response_model=MessageOut,
    status_code=201,
    summary="Send a message",
)
async def send_message(
    conv_id: int,
    body: MessageCreate,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    conv = await chat_service.get_conversation_or_404(session, conv_id)
    chat_service.require_participant(conv, user.user_id)
    return await chat_service.send_message(session, db, redis_pub.client, conv, user.user_id, body.text)


@router.patch(
    "/{conv_id}/read",
    status_code=204,
    summary="Mark messages as read up to message_id",
)
async def mark_read(
    conv_id: int,
    body: ReadBody,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    conv = await chat_service.get_conversation_or_404(session, conv_id)
    chat_service.require_participant(conv, user.user_id)
    await chat_repo.mark_read_up_to(db, conv_id, user.user_id, body.message_id)


@router.delete(
    "/{conv_id}/messages/{message_id}",
    status_code=204,
    summary="Soft-delete own message",
)
async def delete_message(
    conv_id: int,
    message_id: str,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    conv = await chat_service.get_conversation_or_404(session, conv_id)
    chat_service.require_participant(conv, user.user_id)
    await chat_repo.soft_delete_message(db, message_id, user.user_id)
