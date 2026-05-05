from fastapi import APIRouter

from app.api.v1.assignments import router as assignments_router
from app.api.v1.health import router as health_router
from app.api.v1.questions import router as questions_router
from app.api.v1.submissions import router as submissions_router
from app.api.v1.widgets import router as widgets_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(widgets_router)
router.include_router(assignments_router)
router.include_router(questions_router)
router.include_router(submissions_router)
