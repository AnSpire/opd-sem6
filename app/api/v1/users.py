from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_session
from app.deps import UserContext, get_current_user
from app.schemas.chat import ProfileOut, ProfileUpsert
from app.services import chat as chat_service

router = APIRouter(prefix="/users", tags=["users"])


@router.put("/me/profile", response_model=ProfileOut, summary="Upsert own profile")
async def upsert_my_profile(
    body: ProfileUpsert,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    profile = await chat_service.upsert_profile(session, user.user_id, body.display_name, body.avatar_url)
    return ProfileOut.model_validate(profile)


@router.get("/{user_id}/profile", response_model=ProfileOut, summary="Get user profile by ID")
async def get_user_profile(
    user_id: int,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    profile = await chat_service.get_profile_or_404(session, user_id)
    return ProfileOut.model_validate(profile)
