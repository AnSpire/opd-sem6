from fastapi import APIRouter, Response
from sqlalchemy import text

from app.db import mongo, postgres

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe — проверяет подключения к Postgres и MongoDB")
async def readyz(response: Response):
    checks: dict[str, str] = {}
    ok = True

    try:
        async with postgres.AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = str(exc)
        ok = False

    try:
        await mongo.get_client().admin.command("ping")
        checks["mongo"] = "ok"
    except Exception as exc:
        checks["mongo"] = str(exc)
        ok = False

    if not ok:
        response.status_code = 503
        return {"status": "degraded", "checks": checks}

    return {"status": "ok", "checks": checks}
