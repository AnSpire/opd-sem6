from fastapi import HTTPException

from app.deps import UserContext
from app.models.widget import Widget


def require_teacher(user: UserContext) -> None:
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher role required")


def require_widget_owner(widget: Widget, user: UserContext) -> None:
    if widget.creator_user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Not the widget owner")
