from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    assert client is not None, "MongoDB client not initialised"
    return client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db]
