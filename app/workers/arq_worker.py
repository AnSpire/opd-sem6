import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from arq import cron
from arq.connections import RedisSettings
from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.repositories import ai_logs as ai_logs_repo
from app.repositories import submissions as sub_repo
from app.services import ai_grader
from app.services import assignments as assignment_service
from app.services import homework as hw_service
from app.services import stats as stats_service

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    ctx["mongo"] = AsyncIOMotorClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    ctx["db"] = ctx["mongo"][settings.mongo_db]
    ctx["pg_engine"] = create_async_engine(str(settings.postgres_dsn))
    ctx["session_factory"] = async_sessionmaker(ctx["pg_engine"], expire_on_commit=False)


async def shutdown(ctx: dict) -> None:
    ctx["mongo"].close()
    await ctx["pg_engine"].dispose()


async def grade_submission(ctx: dict, submission_id: str) -> None:
    db = ctx["db"]
    session_factory = ctx["session_factory"]

    submission = await sub_repo.get_by_id(db, submission_id)
    if not submission:
        logger.warning("grade_submission: submission %s not found, skipping", submission_id)
        return

    start = time.monotonic()
    log_request: dict = {}
    log_response: dict = {}
    log_status = "ok"
    log_error: str | None = None
    ai_grading: dict | None = None

    try:
        async with session_factory() as session:
            assignment = await assignment_service.get_assignment_or_404(session, submission["assignment_id"])
            hw_details = await hw_service.get_homework_details_or_404(session, submission["assignment_id"])

        log_request = {
            "prompt": hw_details.prompt,
            "model": "gemini-2.5-flash",
            "assignment_id": submission["assignment_id"],
        }

        result = await ai_grader.grade_homework(submission, hw_details, assignment)

        log_response = result.model_dump()
        ai_grading = {
            "score": result.score,
            "max_score": assignment.max_score,
            "feedback": result.feedback,
            "rubric_breakdown": [rb.model_dump() for rb in result.rubric_breakdown],
            "graded_at": datetime.now(timezone.utc),
            "log_id": None,
        }
        await sub_repo.update_grading(db, submission_id, "pending_teacher", ai_grading)
        logger.info("grade_submission: %s graded successfully, score=%s/%s", submission_id, result.score, assignment.max_score)

    except (ValueError, json.JSONDecodeError) as e:
        log_status = "parse_error"
        log_error = str(e)
        logger.warning("grade_submission: parse error for %s: %s", submission_id, e)
        await sub_repo.update_grading(db, submission_id, "pending_teacher")

    except asyncio.TimeoutError:
        log_status = "timeout"
        log_error = "Gemini API timeout"
        logger.warning("grade_submission: timeout for %s", submission_id)
        await sub_repo.update_grading(db, submission_id, "pending_teacher")

    except Exception as e:
        log_status = "api_error"
        log_error = str(e)
        logger.error("grade_submission: unexpected error for %s: %s", submission_id, e)
        await sub_repo.update_grading(db, submission_id, "pending_teacher")

    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        await ai_logs_repo.create_log(
            db,
            submission_id=submission_id,
            assignment_id=submission["assignment_id"],
            widget_id=submission["widget_id"],
            request_data=log_request,
            response_data=log_response,
            latency_ms=latency_ms,
            status=log_status,
            error=log_error,
        )


async def run_send_metrics(ctx: dict) -> None:
    async with ctx["session_factory"]() as session:
        await stats_service.send_metrics(session, ctx["db"])


class WorkerSettings:
    functions = [grade_submission]
    cron_jobs = [cron(run_send_metrics, minute={0, 10, 20, 30, 40, 50})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
