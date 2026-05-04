from dataclasses import dataclass
from typing import Literal

from fastapi import Header, HTTPException


@dataclass
class UserContext:
    user_id: int
    role: Literal["teacher", "student"]
    board_id: int | None
    widget_id: int | None


async def get_current_user(
    x_user_id: int = Header(...),
    x_user_role: str = Header(...),
    x_board_id: int | None = Header(None),
    x_widget_id: int | None = Header(None),
) -> UserContext:
    if x_user_role not in ("teacher", "student"):
        raise HTTPException(status_code=400, detail="Invalid X-User-Role")
    return UserContext(
        user_id=x_user_id,
        role=x_user_role,  # type: ignore[arg-type]
        board_id=x_board_id,
        widget_id=x_widget_id,
    )
