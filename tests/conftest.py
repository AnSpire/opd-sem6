import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


load_dotenv(Path(__file__).parent.parent / ".env.test", override=True)

from app.config import settings
print(f">>> MONGO_URI = {settings.mongo_uri}")
print(f">>> POSTGRES_DSN = {settings.postgres_dsn}")
from app.db import mongo
from app.main import app

# ---------------------------------------------------------------------------
# HTTP header presets
# ---------------------------------------------------------------------------

TEACHER_HEADERS = {"x-user-id": "1", "x-user-role": "teacher", "x-board-id": "10", "x-widget-id": "1"}
STUDENT_HEADERS = {"x-user-id": "2", "x-user-role": "student", "x-board-id": "10", "x-widget-id": "1"}
OTHER_TEACHER_HEADERS = {"x-user-id": "99", "x-user-role": "teacher", "x-board-id": "20", "x-widget-id": "99"}


# ---------------------------------------------------------------------------
# App resources — session-scoped: ASGITransport does not trigger FastAPI lifespan
# ---------------------------------------------------------------------------
import subprocess
import os

@pytest_asyncio.fixture(scope="session", autouse=True)
async def app_startup():
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env={**os.environ},
    )
    mongo.client = AsyncIOMotorClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
    )
    yield
    mongo.client.close()


# ---------------------------------------------------------------------------
# HTTP client — session-scoped: lifespan starts once for the whole test run
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def client(app_startup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# DB teardown — standalone asyncpg connection, no cross-scope dependencies
# ---------------------------------------------------------------------------

def _pg_dsn() -> str:
    return str(settings.postgres_dsn).replace("postgresql+asyncpg://", "postgresql://")


@pytest_asyncio.fixture(autouse=True)
async def clean_db(app_startup):
    conn = await asyncpg.connect(_pg_dsn())
    try:
        await conn.execute("TRUNCATE TABLE widgets CASCADE")
    finally:
        await conn.close()
    from app.db.mongo import get_db
    await get_db().submissions.delete_many({})
    yield


# ---------------------------------------------------------------------------
# Header fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def teacher_headers():
    return TEACHER_HEADERS


@pytest.fixture
def student_headers():
    return STUDENT_HEADERS


@pytest.fixture
def other_teacher_headers():
    return OTHER_TEACHER_HEADERS


# ---------------------------------------------------------------------------
# Domain object fixtures
# ---------------------------------------------------------------------------

WIDGET_PAYLOAD = {"id": 1, "board_id": 10}

ASSIGNMENT_PAYLOAD = {
    "type": "test",
    "title": "Quiz #1",
    "description": "Basic quiz",
    "max_score": 10,
    "final_score_strategy": "best",
}

QUESTION_PAYLOAD = {
    "order": 1,
    "text": "What is 2 + 2?",
    "type": "single",
    "options": ["3", "4", "5"],
    "correct_answer": ["4"],
    "points": 5,
    "short_text_match": "exact",
}


@pytest_asyncio.fixture
async def widget(client, teacher_headers):
    r = await client.post("/api/v1/widgets", json=WIDGET_PAYLOAD, headers=teacher_headers)
    assert r.status_code == 201
    return r.json()


@pytest_asyncio.fixture
async def assignment(client, widget, teacher_headers):
    r = await client.post(
        f"/api/v1/widgets/{widget['id']}/assignments",
        json=ASSIGNMENT_PAYLOAD,
        headers=teacher_headers,
    )
    assert r.status_code == 201
    return r.json()["assignment"]


@pytest_asyncio.fixture
async def question(client, assignment, teacher_headers):
    r = await client.post(
        f"/api/v1/assignments/{assignment['id']}/questions",
        json=QUESTION_PAYLOAD,
        headers=teacher_headers,
    )
    assert r.status_code == 201
    return r.json()
