import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.db import mongo
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def init_mongo():
    mongo.client = AsyncIOMotorClient(settings.mongo_uri)
    yield
    mongo.client.close()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
