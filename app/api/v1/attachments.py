from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import require_widget_owner
from app.db.mongo import get_db
from app.db.postgres import get_session
from app.deps import UserContext, get_current_user
from app.repositories import submissions as sub_repo
from app.services import assignments as assignment_service
from app.services import storage
from app.services import widgets as widget_service

router = APIRouter(tags=["attachments"])


@router.get(
    "/attachments/{submission_id}/{attachment_index}",
    summary="Получить presigned URL для вложения сабмишена (TTL 5 мин)",
)
async def get_attachment(
    submission_id: str,
    attachment_index: int,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    doc = await sub_repo.get_by_id_or_404(db, submission_id)

    if user.role == "teacher":
        assignment = await assignment_service.get_assignment_or_404(session, doc["assignment_id"])
        widget = await widget_service.get_widget_or_404(session, assignment.widget_id)
        require_widget_owner(widget, user)
    else:
        if doc["student_user_id"] != user.user_id:
            raise HTTPException(status_code=403, detail="Access denied")

    attachments = doc.get("payload", {}).get("attachments", [])
    if attachment_index < 0 or attachment_index >= len(attachments):
        raise HTTPException(status_code=404, detail="Attachment not found")

    key = attachments[attachment_index]["s3_key"]
    url = await storage.presigned_get_url(key, ttl=300)
    return {"url": url}
