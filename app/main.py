import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy import text

from app.api.v1 import router as api_v1_router
from app.config import settings
from app.db import mongo, postgres
from app.repositories.submissions import ensure_indexes
from app.services.storage import ensure_bucket

logger = logging.getLogger(__name__)


async def _ping(coro, name: str) -> None:
    try:
        await asyncio.wait_for(coro, timeout=2.0)
        logger.info("%s: connected", name)
    except Exception as e:
        logger.warning("%s: unavailable — %s", name, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo.client = AsyncIOMotorClient(settings.mongo_uri, serverSelectionTimeoutMS=2000)
    redis_client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)

    async with postgres.AsyncSessionLocal() as session:
        await _ping(session.execute(text("SELECT 1")), "postgres")
    await _ping(mongo.client.admin.command("ping"), "mongo")
    await _ping(redis_client.ping(), "redis")
    await redis_client.aclose()
    await ensure_indexes(mongo.get_db())
    await _ping(ensure_bucket(), "minio")

    yield

    mongo.client.close()
    await postgres.engine.dispose()


app = FastAPI(title="homework-widget-backend", lifespan=lifespan)
app.include_router(api_v1_router)
