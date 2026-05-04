from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WidgetCreate(BaseModel):
    id: int
    board_id: int


class WidgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int
    creator_user_id: int
    created_at: datetime
    updated_at: datetime
