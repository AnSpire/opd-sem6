from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from app.api.v1 import router as api_v1_router
from app.config import settings
from app.db import mongo, postgres


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo.client = AsyncIOMotorClient(settings.mongo_uri)
    redis_client = aioredis.from_url(settings.redis_url)

    try:
        await mongo.client.admin.command("ping")
        async with postgres.AsyncSessionLocal() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        await redis_client.ping()
    finally:
        await redis_client.aclose()

    yield

    mongo.client.close()
    await postgres.engine.dispose()


app = FastAPI(title="homework-widget-backend", lifespan=lifespan)
app.include_router(api_v1_router)
