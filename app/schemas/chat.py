from datetime import datetime

from pydantic import BaseModel, Field


class ProfileUpsert(BaseModel):
    display_name: str = Field(..., max_length=255)
    avatar_url: str | None = None


class ProfileOut(BaseModel):
    user_id: int
    display_name: str
    avatar_url: str | None

    model_config = {"from_attributes": True}


class ConversationCreate(BaseModel):
    other_user_id: int
    board_id: int


class MessageOut(BaseModel):
    id: str
    conversation_id: int
    sender_id: int
    text: str
    created_at: datetime
    read_at: datetime | None
    deleted_at: datetime | None


class ConversationOut(BaseModel):
    id: int
    board_id: int
    user1_id: int
    user2_id: int
    created_at: datetime
    last_msg_at: datetime | None
    last_message: MessageOut | None = None
    unread_count: int = 0

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)


class ReadBody(BaseModel):
    message_id: str
