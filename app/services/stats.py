import asyncio
import logging
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.assignment import Assignment
from app.models.stats_module import StatsModule
from app.models.widget import Widget
from app.services.proxy_client import get_http_client

logger = logging.getLogger(__name__)


async def _load_module(session: AsyncSession) -> StatsModule | None:
    result = await session.execute(select(StatsModule).where(StatsModule.is_enabled.is_(True)))
    return result.scalar_one_or_none()


async def register_module(session: AsyncSession) -> None:
    if not settings.stats_service_url:
        return

    existing = await _load_module(session)
    if existing:
        logger.info("stats: module already registered (module_id=%s)", existing.module_id)
        return

    async with get_http_client() as client:
        try:
            resp = await client.post(
                f"{settings.stats_service_url}/api/stats/module/create",
                json={"name": settings.stats_module_name},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("stats: register_module failed — %s", e)
            return

    data = resp.json()
    record = StatsModule(
        module_id=data["module_id"],
        module_name=settings.stats_module_name,
        token=data["token"],
        token_expired=datetime.fromisoformat(data["token_expired"]),
        is_enabled=True,
    )
    session.add(record)
    await session.commit()
    logger.info("stats: module registered (module_id=%s)", record.module_id)


async def send_metrics(session: AsyncSession, db: AsyncIOMotorDatabase) -> None:
    if not settings.stats_service_url:
        return

    module = await _load_module(session)
    if not module:
        await register_module(session)
        module = await _load_module(session)
        if not module:
            logger.warning("stats: send_metrics skipped — no module registration")
            return

    result = await session.execute(select(Widget.id))
    widget_ids = [row[0] for row in result.all()]
    if not widget_ids:
        return

    metrics = []
    for widget_id in widget_ids:
        count_result = await session.execute(
            select(func.count()).select_from(Assignment).where(Assignment.widget_id == widget_id)
        )
        assignments_count = count_result.scalar_one()

        submissions_count = await db.submissions.count_documents({"widget_id": widget_id})
        graded_count = await db.submissions.count_documents(
            {"widget_id": widget_id, "status": {"$in": ["graded", "auto_graded"]}}
        )

        avg_cursor = db.submissions.aggregate([
            {"$match": {"widget_id": widget_id, "grading.final.score": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": None, "avg": {"$avg": "$grading.final.score"}}},
        ])
        avg_docs = await avg_cursor.to_list(length=1)
        average_score = round(avg_docs[0]["avg"], 2) if avg_docs else None

        last_doc = await db.submissions.find_one(
            {"widget_id": widget_id}, sort=[("submitted_at", -1)]
        )
        last_activity = last_doc["submitted_at"].isoformat() if last_doc else None

        metrics.append({
            "widgetId": widget_id,
            "assignmentsCount": assignments_count,
            "submissionsCount": submissions_count,
            "gradedCount": graded_count,
            "averageScore": average_score,
            "lastActivityAt": last_activity,
        })

    await _put_metrics(session, module, metrics)


async def _put_metrics(session: AsyncSession, module: StatsModule, metrics: list[dict]) -> None:
    async with get_http_client() as client:
        try:
            resp = await client.put(
                f"{settings.stats_service_url}/api/stats/module/metrics",
                json=metrics,
                headers={"Authorization": f"Bearer {module.token}"},
            )
        except Exception as e:
            logger.warning("stats: send_metrics HTTP error — %s", e)
            return

    if resp.status_code == 200:
        logger.info("stats: metrics sent for %d widgets", len(metrics))
    elif resp.status_code == 401:
        logger.warning("stats: 401 — re-registering module")
        module.is_enabled = False
        await session.commit()
        await register_module(session)
        new_module = await _load_module(session)
        if new_module:
            async with get_http_client() as client:
                try:
                    await client.put(
                        f"{settings.stats_service_url}/api/stats/module/metrics",
                        json=metrics,
                        headers={"Authorization": f"Bearer {new_module.token}"},
                    )
                except Exception as e:
                    logger.warning("stats: retry after re-register failed — %s", e)
    elif resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        logger.warning("stats: 429 rate limited — sleeping %ds", retry_after)
        await asyncio.sleep(retry_after)
    else:
        logger.warning("stats: unexpected response status %d", resp.status_code)
