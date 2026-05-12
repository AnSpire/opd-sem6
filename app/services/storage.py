import asyncio
import io
from datetime import timedelta
from functools import partial

from minio import Minio

from app.config import settings

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
    return _client


async def ensure_bucket() -> None:
    loop = asyncio.get_running_loop()
    client = _get_client()
    bucket = settings.minio_bucket
    exists = await loop.run_in_executor(None, client.bucket_exists, bucket)
    if not exists:
        await loop.run_in_executor(None, client.make_bucket, bucket)


async def upload_object(key: str, data: bytes, content_type: str) -> None:
    loop = asyncio.get_running_loop()
    client = _get_client()
    fn = partial(
        client.put_object,
        settings.minio_bucket,
        key,
        io.BytesIO(data),
        len(data),
        content_type=content_type,
    )
    await loop.run_in_executor(None, fn)


async def delete_object(key: str) -> None:
    loop = asyncio.get_running_loop()
    client = _get_client()
    fn = partial(client.remove_object, settings.minio_bucket, key)
    await loop.run_in_executor(None, fn)


async def presigned_get_url(key: str, ttl: int = 300) -> str:
    loop = asyncio.get_running_loop()
    client = _get_client()
    fn = partial(
        client.presigned_get_object,
        settings.minio_bucket,
        key,
        timedelta(seconds=ttl),
    )
    return await loop.run_in_executor(None, fn)
